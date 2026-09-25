from __future__ import annotations

import logging
from typing import Any

import great_expectations as gx
import pandas as pd

from core.config import Settings
from core.utils import now_utc, write_json

MIN_ROWS = 5
MAX_ROWS = 5000
MIN_SUMMARY_CHARS = 30
REQUIRED_COLUMNS = ["paper_id", "title", "text_for_embedding"]
MAX_STALE_RATIO = 0.25

# GX 1.x in progress bar/log INFO rat nhieu khi validate, tat bot de console gon.
logging.getLogger("great_expectations").setLevel(logging.WARNING)


def _build_expectations() -> list[gx.expectations.Expectation]:
    expectations: list[gx.expectations.Expectation] = [
        gx.expectations.ExpectTableRowCountToBeBetween(min_value=MIN_ROWS, max_value=MAX_ROWS),
    ]
    expectations += [gx.expectations.ExpectColumnValuesToNotBeNull(column=column) for column in REQUIRED_COLUMNS]
    expectations += [
        gx.expectations.ExpectColumnValuesToBeUnique(column="paper_id"),
        gx.expectations.ExpectColumnValueLengthsToBeBetween(column="summary", min_value=MIN_SUMMARY_CHARS),
    ]
    return expectations


def _prepare_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Chuan hoa chuoi rong thanh null de ExpectColumnValuesToNotBeNull bat duoc ca blank value.

    `summary` thi nguoc lai: null -> "" vi GX bo qua null khi check do dai, blank summary se lot luoi.
    """
    prepared = df.copy()
    for column in REQUIRED_COLUMNS:
        if column not in prepared.columns:
            prepared[column] = None
        prepared[column] = prepared[column].map(
            lambda value: None if value is None or (isinstance(value, str) and not value.strip()) else value
        )
    summary = prepared["summary"] if "summary" in prepared.columns else pd.Series("", index=prepared.index)
    prepared["summary"] = summary.fillna("").astype(str).str.strip()
    return prepared


def _age_days(df: pd.DataFrame) -> pd.Series:
    if "age_days" in df.columns:
        return pd.to_numeric(df["age_days"], errors="coerce")
    published = pd.to_datetime(df["published"], errors="coerce", utc=True)
    return (pd.Timestamp(now_utc()) - published).dt.days


def _freshness_summary(df: pd.DataFrame, settings: Settings) -> dict[str, Any]:
    published = pd.to_datetime(df["published"], errors="coerce", utc=True)
    age_days = _age_days(df)
    total_rows = int(len(df))
    stale_rows = int((age_days > settings.freshness_threshold_days).sum())
    stale_ratio = stale_rows / total_rows if total_rows else 1.0
    return {
        "latest_published": published.max().date().isoformat() if published.notna().any() else None,
        "oldest_published": published.min().date().isoformat() if published.notna().any() else None,
        "threshold_days": settings.freshness_threshold_days,
        "max_stale_ratio": MAX_STALE_RATIO,
        "stale_rows": stale_rows,
        "total_rows": total_rows,
        "stale_ratio": round(stale_ratio, 4),
        "is_fresh": stale_ratio <= MAX_STALE_RATIO,
    }


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    context = gx.get_context(mode="ephemeral")
    data_source = context.data_sources.add_pandas(name="papers_source")
    data_asset = data_source.add_dataframe_asset(name="papers_asset")
    batch_def = data_asset.add_batch_definition_whole_dataframe("papers_batch")
    batch = batch_def.get_batch(batch_parameters={"dataframe": _prepare_frame(df)})

    suite = context.suites.add(gx.ExpectationSuite(name=f"{report_name}_papers_suite"))
    for expectation in _build_expectations():
        suite.add_expectation(expectation)
    validation = batch.validate(suite)

    checks = []
    for result in validation.results:
        config = result.expectation_config
        observed = result.result or {}
        checks.append(
            {
                "expectation": config.type,
                "column": config.kwargs.get("column"),
                "success": bool(result.success),
                "observed_value": observed.get("observed_value"),
                "unexpected_count": observed.get("unexpected_count"),
                "unexpected_percent": observed.get("unexpected_percent"),
            }
        )

    freshness = _freshness_summary(df, settings)
    warnings = []
    if not freshness["is_fresh"]:
        warnings.append(
            f"Stale data: {freshness['stale_ratio']:.0%} rows older than {settings.freshness_threshold_days} days "
            f"(limit {MAX_STALE_RATIO:.0%}) - refresh the source."
        )

    report = {
        "report_name": report_name,
        "generated_at": now_utc().isoformat(),
        "engine": f"great_expectations {gx.__version__}",
        "success": bool(validation.success),
        "row_count": int(len(df)),
        "evaluated_expectations": len(checks),
        "failed_expectations": sum(not check["success"] for check in checks),
        "checks": checks,
        "freshness": freshness,
        "warnings": warnings,
    }
    write_json(settings.paths.quality_dir / f"{report_name}_quality_report.json", report)
    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    payload = {"generated_at": now_utc().isoformat(), **_freshness_summary(df, settings)}
    write_json(report_path, payload)
    return payload
