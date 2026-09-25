from __future__ import annotations

from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import now_utc, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import load_or_create_test_set
from ingestion.cleaning import build_clean_dataframe, save_clean_dataframe
from ingestion.crossref import fetch_source_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.agent import build_agent, run_agent_question
from retrieval.index import LocalEmbeddingIndex

DEMO_SAMPLE_COUNT = 2


def _ensure_test_set(df: pd.DataFrame, settings: Settings) -> list[dict[str, Any]]:
    """Dung lai test set co dinh; chi sinh lai khi REFRESH_TEST_SET=1 hoac ground truth khong con trong corpus."""
    test_set = load_or_create_test_set(df, settings.paths.eval_testset, refresh=settings.refresh_test_set)
    known_ids = set(df["paper_id"])
    if any(doc_id not in known_ids for sample in test_set.samples for doc_id in sample["ground_truth_doc_ids"]):
        print("[phase1] Test set references papers missing from the corpus -> regenerating.")
        test_set = load_or_create_test_set(df, settings.paths.eval_testset, refresh=True)
    return test_set.samples


def _short_error(error: Exception, limit: int = 160) -> str:
    """Loi provider (vd 429 cua Gemini) kem ca JSON dai -> chi giu phan dau de report doc duoc."""
    message = str(error).splitlines()[0] if str(error) else type(error).__name__
    return message if len(message) <= limit else message[:limit] + "..."


def _run_agent_demo(settings: Settings, index: LocalEmbeddingIndex, samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        agent = build_agent(settings, index)
    except Exception as error:
        return [{"error": f"Agent unavailable: {_short_error(error)}"}]

    demo: list[dict[str, Any]] = []
    for sample in samples[:DEMO_SAMPLE_COUNT]:
        entry = {"id": sample["id"], "question": sample["question"], "ground_truth": sample["ground_truth"]}
        try:
            entry["agent_answer"] = run_agent_question(agent, sample["question"])
        except Exception as error:
            entry["error"] = f"Agent call failed: {_short_error(error)}"
        demo.append(entry)
    return demo


def main() -> None:
    settings = load_settings()
    run_date = now_utc()
    print(f"[phase1] Run date: {run_date.isoformat()}")

    records = fetch_source_records(settings)
    print(f"[phase1] 1/7 Ingested {len(records)} raw records -> {settings.paths.raw_records_json}")

    df = build_clean_dataframe(records, run_date)
    save_clean_dataframe(df, settings.paths.clean_csv, settings.paths.clean_json)
    print(f"[phase1] 2/7 Cleaned {len(df)} rows -> {settings.paths.clean_csv}")

    quality = run_data_quality_checks(df, settings, "baseline")
    freshness = build_freshness_report(df, settings, settings.paths.freshness_report)
    print(
        f"[phase1] 3/7 Quality gate success={quality['success']} "
        f"({quality['failed_expectations']}/{quality['evaluated_expectations']} failed), is_fresh={freshness['is_fresh']}"
    )
    if not quality["success"]:
        raise RuntimeError(
            f"Data quality gate failed - refusing to index bad data. See {settings.paths.baseline_quality_report}"
        )

    index = LocalEmbeddingIndex.build(df, settings)
    print(f"[phase1] 4/7 Indexed {len(index.documents)} documents into Chroma collection '{index.collection_name}'")

    samples = _ensure_test_set(df, settings)
    print(f"[phase1] 5/7 Test set: {len(samples)} questions -> {settings.paths.eval_testset}")

    bundle = evaluate_pipeline(
        settings,
        index,
        settings.paths.eval_testset,
        settings.paths.baseline_metrics,
        settings.paths.baseline_answers,
    )
    metrics = bundle.summary
    print(
        f"[phase1] 6/7 Baseline hit_rate={metrics['retrieval_hit_rate']:.2f} "
        f"token_f1={metrics['mean_token_f1']:.2f} judge_accuracy={metrics['judge_accuracy']:.2f} "
        f"(heuristic fallback on {metrics['judge_fallback_count']}/{metrics['samples']})"
    )

    demo = _run_agent_demo(settings, index, samples)
    write_json(settings.paths.demo_answers, demo)

    source_summary = {
        "source_api": settings.source_api,
        "source_mode": "live API (falls back to snapshot on error)" if settings.refresh_source else "offline snapshot",
        "source_query": settings.source_query,
        "source_filter": settings.source_filter,
        "run_date": run_date.isoformat(),
        "raw_records": len(records),
        "clean_rows": len(df),
        "dropped_rows": len(records) - len(df),
        "embedding_model": settings.embedding_model,
        "collection_name": index.collection_name,
        "top_k": settings.top_k,
        "llm": f"{settings.llm_provider} / {settings.model_name}",
        "agent_demo": demo,
    }
    generate_phase1_report(settings.paths.baseline_report, source_summary, metrics, quality, freshness)
    print(f"[phase1] 7/7 Report -> {settings.paths.baseline_report}")
