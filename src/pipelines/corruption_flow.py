from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import now_utc, read_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe, save_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from retrieval.index import LocalEmbeddingIndex

# age_days phu thuoc ngay chay nen khong dung de so sanh repaired voi baseline.
IDEMPOTENCY_COLUMNS = ["paper_id", "title", "summary", "authors_joined", "categories_joined", "published", "text_for_embedding"]


def _evaluate_state(
    settings: Settings,
    label: str,
    df: pd.DataFrame,
    embeddings_path: Path,
    metrics_path: Path,
    answers_path: Path,
) -> dict[str, Any]:
    index = LocalEmbeddingIndex.build(df, settings, embeddings_path)
    print(f"[corruption] {label}: indexed {len(index.documents)} documents into '{index.collection_name}'")
    metrics = evaluate_pipeline(settings, index, settings.paths.eval_testset, metrics_path, answers_path).summary
    print(
        f"[corruption] {label}: hit_rate={metrics['retrieval_hit_rate']:.2f} token_f1={metrics['mean_token_f1']:.2f} "
        f"judge_accuracy={metrics['judge_accuracy']:.2f} (heuristic fallback on {metrics['judge_fallback_count']}/{metrics['samples']})"
    )
    return metrics


def _check_quality(settings: Settings, label: str, df: pd.DataFrame) -> tuple[dict[str, Any], dict[str, Any]]:
    quality = run_data_quality_checks(df, settings, label)
    freshness = build_freshness_report(df, settings, settings.paths.quality_dir / f"{label}_freshness_report.json")
    failed = [f"{check['expectation']}({check['column'] or 'table'})" for check in quality["checks"] if not check["success"]]
    print(
        f"[corruption] {label}: quality gate success={quality['success']} failed={failed or '-'} "
        f"is_fresh={freshness['is_fresh']} ({freshness['stale_rows']}/{freshness['total_rows']} stale)"
    )
    return quality, freshness


def _matches_baseline(repaired: pd.DataFrame, baseline: pd.DataFrame) -> bool:
    def canonical(df: pd.DataFrame) -> pd.DataFrame:
        frame = df[IDEMPOTENCY_COLUMNS].astype(str)
        return frame.sort_values("paper_id").reset_index(drop=True)

    return canonical(repaired).equals(canonical(baseline))


def _print_comparison(baseline: dict[str, Any], corrupted: dict[str, Any], repaired: dict[str, Any]) -> None:
    rows = [
        ("retrieval_hit_rate", "Retrieval hit rate"),
        ("mean_token_f1", "Mean token F1"),
        ("judge_accuracy", "Judge accuracy"),
        ("mean_judge_score", "Mean judge score"),
    ]
    print("\n| Metric | Baseline | Corrupted | Repaired |")
    print("|---|---|---|---|")
    for key, label in rows:
        print(f"| {label} | {baseline[key]:.2f} | {corrupted[key]:.2f} | {repaired[key]:.2f} |")
    print()


def main() -> None:
    settings = load_settings()
    paths = settings.paths
    run_date = now_utc()
    if not paths.baseline_metrics.exists() or not paths.clean_json.exists() or not paths.eval_testset.exists():
        raise RuntimeError("Baseline artifacts missing - run `python script/run_phase1.py` first.")

    # 1. Baseline.
    baseline_metrics = read_json(paths.baseline_metrics)
    baseline_df = pd.read_json(paths.clean_json)
    print(f"[corruption] Baseline: {len(baseline_df)} rows, hit_rate={baseline_metrics['retrieval_hit_rate']:.2f}")

    # 2-3. Corrupt + luu artifacts.
    corrupted_df = corrupt_clean_dataframe(baseline_df, paths.corruption_log)
    save_clean_dataframe(corrupted_df, paths.corrupted_clean_csv, paths.corrupted_clean_json)
    print(f"[corruption] Corrupted: {len(corrupted_df)} rows (6 scenarios) -> {paths.corruption_log}")

    # 4-5. Quality gate tren du lieu ban. Production se chan o day; lab van index de do Silent Failure.
    corrupted_quality, corrupted_freshness = _check_quality(settings, "corrupted", corrupted_df)
    if not corrupted_quality["success"]:
        print("[corruption] Gate FAILED -> production would stop here; indexing anyway to measure the damage.")
    corrupted_metrics = _evaluate_state(
        settings, "corrupted", corrupted_df, paths.corrupted_embeddings_json, paths.corrupted_metrics, paths.corrupted_answers
    )

    # 6. Idempotent repair: dung lai tu raw records (nguon tin cay), khong va vao ban clean bi hong.
    repaired_df = build_clean_dataframe(load_raw_records(paths.raw_records_json), run_date)
    save_clean_dataframe(repaired_df, paths.repaired_clean_csv, paths.repaired_clean_json)
    repaired_quality, repaired_freshness = _check_quality(settings, "repaired", repaired_df)
    if not repaired_quality["success"]:
        raise RuntimeError(f"Repaired data still fails the quality gate - see {paths.quality_dir / 'repaired_quality_report.json'}")
    matches_baseline = _matches_baseline(repaired_df, baseline_df)
    print(f"[corruption] Repaired: {len(repaired_df)} rows rebuilt from raw, identical to baseline={matches_baseline}")

    # 7. Evaluate repaired.
    repaired_metrics = _evaluate_state(
        settings, "repaired", repaired_df, paths.repaired_embeddings_json, paths.repaired_metrics, paths.repaired_answers
    )

    # 8. Report.
    _print_comparison(baseline_metrics, corrupted_metrics, repaired_metrics)
    generate_corruption_report(
        paths.comparison_report,
        baseline_metrics,
        corrupted_metrics,
        repaired_metrics,
        corrupted_quality,
        repaired_quality,
        corrupted_freshness,
        repaired_freshness,
        corruption_log=read_json(paths.corruption_log),
        repair_summary={
            "run_date": run_date.isoformat(),
            "source": str(paths.raw_records_json),
            "rows": len(repaired_df),
            "matches_baseline": matches_baseline,
        },
    )
    print(f"[corruption] Report -> {paths.comparison_report}")
