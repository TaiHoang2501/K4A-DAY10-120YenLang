from __future__ import annotations

from pathlib import Path
from typing import Any

from core.utils import write_text


def _status(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _cell(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(_cell(value) for value in row) + " |" for row in rows]
    return lines


def _quality_section(quality: dict[str, Any]) -> list[str]:
    lines = [
        f"- Engine: `{quality.get('engine', 'great_expectations')}` (ephemeral context)",
        f"- Gate status: **{_status(quality['success'])}** "
        f"({quality['failed_expectations']}/{quality['evaluated_expectations']} expectations failed, "
        f"{quality['row_count']} rows)",
        "",
    ]
    rows = [
        [check["expectation"], check["column"], _status(check["success"]), check["observed_value"], check["unexpected_count"]]
        for check in quality["checks"]
    ]
    return lines + _table(["Expectation", "Column", "Status", "Observed", "Unexpected"], rows)


def _freshness_section(freshness: dict[str, Any]) -> list[str]:
    return _table(
        ["Latest published", "Oldest published", "Stale rows", "Stale ratio", "SLA", "Status"],
        [
            [
                freshness["latest_published"],
                freshness["oldest_published"],
                f"{freshness['stale_rows']}/{freshness['total_rows']}",
                f"{freshness['stale_ratio']:.1%}",
                f"<= {freshness['max_stale_ratio']:.0%} older than {freshness['threshold_days']} days",
                "FRESH" if freshness["is_fresh"] else "STALE",
            ]
        ],
    )


def _metrics_section(metrics: dict[str, Any]) -> list[str]:
    lines = _table(
        ["Samples", "Retrieval hit rate", "Mean token F1", "Judge accuracy", "Mean judge score (1-5)"],
        [
            [
                metrics["samples"],
                metrics["retrieval_hit_rate"],
                metrics["mean_token_f1"],
                metrics["judge_accuracy"],
                metrics["mean_judge_score"],
            ]
        ],
    )
    fallback = metrics.get("judge_fallback_count", 0)
    if fallback:
        lines += [
            "",
            f"> Note: LLM judge unavailable for {fallback}/{metrics['samples']} answers; "
            "those were scored with the token-F1 heuristic fallback.",
        ]
    by_type = metrics.get("by_question_type") or {}
    if by_type:
        lines += ["", "**Breakdown by question type**", ""]
        lines += _table(
            ["Question type", "Samples", "Hit rate", "Token F1", "Judge accuracy"],
            [
                [name, stats["samples"], stats["retrieval_hit_rate"], stats["mean_token_f1"], stats["judge_accuracy"]]
                for name, stats in by_type.items()
            ],
        )
    ragas = metrics.get("ragas") or {}
    if ragas:
        lines += ["", "**Ragas**: " + ", ".join(f"{key}={_cell(value)}" for key, value in ragas.items())]
    return lines


def _demo_section(demo: list[dict[str, Any]]) -> list[str]:
    if not demo:
        return ["_No agent demo was run._"]
    lines: list[str] = []
    for entry in demo:
        if "question" not in entry:
            lines.append(f"- {entry.get('error', 'Agent demo skipped.')}")
            continue
        answer = entry.get("agent_answer") or entry.get("error", "")
        lines += [
            f"- **Q ({entry['id']})**: {entry['question']}",
            f"  - Agent: {_cell(answer)}",
            f"  - Ground truth: {_cell(entry['ground_truth'])}",
        ]
    return lines


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    lines = [
        "# Phase 1 Report - Baseline Pipeline",
        "",
        f"_Generated: {source_summary['run_date']}_",
        "",
        "## 1. Source & Lineage",
        "",
        f"- Source: {source_summary['source_api']} ({source_summary['source_mode']})",
        f"- Query: `{source_summary['source_query']}`",
        f"- Filter: `{source_summary['source_filter']}`",
        f"- Raw records: {source_summary['raw_records']} -> clean rows: {source_summary['clean_rows']} "
        f"(dropped {source_summary['dropped_rows']})",
        f"- Embedding: `{source_summary['embedding_model']}` -> Chroma collection "
        f"`{source_summary['collection_name']}` (top_k={source_summary['top_k']})",
        f"- LLM (judge / agent): `{source_summary['llm']}`",
        "",
        "## 2. Data Quality Gate (Great Expectations 1.x)",
        "",
        *_quality_section(quality),
        "",
        "## 3. Freshness SLA",
        "",
        *_freshness_section(freshness),
        "",
        "## 4. Baseline Evaluation",
        "",
        *_metrics_section(metrics),
        "",
        "## 5. Agent Demo",
        "",
        *_demo_section(source_summary.get("agent_demo", [])),
        "",
    ]
    if quality.get("warnings"):
        lines += ["## Warnings", "", *[f"- {warning}" for warning in quality["warnings"]], ""]
    write_text(Path(report_path), "\n".join(lines))


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
    corruption_log: dict[str, Any] | None = None,
    repair_summary: dict[str, Any] | None = None,
) -> None:
    metric_rows = [
        ("retrieval_hit_rate", "Retrieval hit rate"),
        ("mean_token_f1", "Mean token F1"),
        ("judge_accuracy", "Judge accuracy"),
        ("mean_judge_score", "Mean judge score (1-5)"),
    ]
    states = [("Baseline", baseline_metrics), ("Corrupted", corrupted_metrics), ("Repaired", repaired_metrics)]

    lines = ["# Corruption Report - Baseline vs Corrupted vs Repaired", ""]
    if repair_summary:
        lines += [f"_Generated: {repair_summary['run_date']}_", ""]

    lines += ["## 1. Headline Metrics", ""]
    lines += _table(
        ["Metric", "Baseline", "Corrupted", "Repaired", "Corrupted vs Baseline", "Repaired vs Baseline"],
        [
            [
                label,
                baseline_metrics[key],
                corrupted_metrics[key],
                repaired_metrics[key],
                f"{corrupted_metrics[key] - baseline_metrics[key]:+.2f}",
                f"{repaired_metrics[key] - baseline_metrics[key]:+.2f}",
            ]
            for key, label in metric_rows
        ],
    )
    fallbacks = [f"{name} {m.get('judge_fallback_count', 0)}/{m['samples']}" for name, m in states]
    lines += ["", f"> Judge answers scored by the heuristic fallback (LLM unavailable): {', '.join(fallbacks)}."]

    by_type = {name: m.get("by_question_type") or {} for name, m in states}
    question_types = list(by_type["Baseline"]) or list(by_type["Corrupted"])
    if question_types:
        lines += ["", "**Token F1 / hit rate by question type**", ""]
        lines += _table(
            ["Question type", "Baseline", "Corrupted", "Repaired"],
            [
                [question_type]
                + [
                    f"{stats['mean_token_f1']:.2f} / {stats['retrieval_hit_rate']:.2f}" if (stats := by_type[name].get(question_type)) else "-"
                    for name, _ in states
                ]
                for question_type in question_types
            ],
        )

    lines += ["", "## 2. Injected Corruption", ""]
    if corruption_log:
        lines += [
            f"Seed `{corruption_log['seed']}`: {corruption_log['input_rows']} rows -> {corruption_log['output_rows']} rows, "
            f"{corruption_log['scenarios']} scenarios.",
            "",
        ]
        lines += _table(
            ["#", "Scenario", "Rows", "Description"],
            [[step["step"], step["name"], step["affected_rows"], step["description"]] for step in corruption_log["steps"]],
        )
    else:
        lines.append("_Corruption log not provided._")

    lines += ["", "## 3. Data Quality Gate (Great Expectations 1.x)", ""]
    expectation_keys = [(check["expectation"], check["column"]) for check in corrupted_quality["checks"]]
    repaired_checks = {(check["expectation"], check["column"]): check for check in repaired_quality["checks"]}
    lines += _table(
        ["Expectation", "Column", "Corrupted", "Repaired"],
        [
            [
                expectation,
                column,
                f"{_status(check['success'])} ({_cell(check['unexpected_count'] if check['unexpected_count'] is not None else check['observed_value'])})",
                _status(repaired_checks[(expectation, column)]["success"]) if (expectation, column) in repaired_checks else "-",
            ]
            for (expectation, column), check in zip(expectation_keys, corrupted_quality["checks"], strict=True)
        ],
    )
    lines += [
        "",
        f"- Gate status: corrupted **{_status(corrupted_quality['success'])}**, repaired **{_status(repaired_quality['success'])}**",
        "",
        "## 4. Freshness SLA",
        "",
    ]
    lines += _table(
        ["State", "Latest published", "Oldest published", "Stale rows", "Stale ratio", "Status"],
        [
            [
                name,
                freshness["latest_published"],
                freshness["oldest_published"],
                f"{freshness['stale_rows']}/{freshness['total_rows']}",
                f"{freshness['stale_ratio']:.1%}",
                "FRESH" if freshness["is_fresh"] else "STALE",
            ]
            for name, freshness in (("Corrupted", corrupted_freshness), ("Repaired", repaired_freshness))
        ],
    )

    lines += ["", "## 5. Repair", ""]
    if repair_summary:
        lines += [
            f"- Rebuilt {repair_summary['rows']} rows from the trusted raw snapshot `{Path(repair_summary['source']).name}` "
            "with the same cleaning code (no patching of the corrupted table).",
            f"- Content identical to baseline (ignoring run-date dependent `age_days`): **{repair_summary['matches_baseline']}**",
        ]
    lines += [
        "",
        "## 6. Conclusion",
        "",
        f"- Corruption dropped retrieval hit rate by {baseline_metrics['retrieval_hit_rate'] - corrupted_metrics['retrieval_hit_rate']:.2f} "
        f"and token F1 by {baseline_metrics['mean_token_f1'] - corrupted_metrics['mean_token_f1']:.2f}; the RAG pipeline still "
        "returned fluent answers (silent failure) - only the quality gate and freshness SLA flagged the problem.",
        f"- Repair restored hit rate to {repaired_metrics['retrieval_hit_rate']:.2f} and token F1 to {repaired_metrics['mean_token_f1']:.2f}.",
        "",
    ]
    write_text(Path(report_path), "\n".join(lines))
