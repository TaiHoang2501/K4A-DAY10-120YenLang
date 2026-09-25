from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import great_expectations as gx
import great_expectations.expectations as gxe
import pandas as pd

from core.config import Settings
from core.utils import write_json

logger = logging.getLogger(__name__)


def run_data_quality_checks(
    df: pd.DataFrame,
    settings: Settings,
    report_name: str = "baseline",
    phase_label: str | None = None,
) -> dict[str, Any]:
    """Chạy 4 Data Quality Expectations bắt buộc bằng GX 1.x API.

    Expectations:
    1. ExpectTableRowCountToBeBetween: 5 – 5000 rows.
    2. ExpectColumnValuesToNotBeNull: paper_id, title, text_for_embedding.
    3. ExpectColumnValuesToBeUnique: paper_id.
    4. ExpectColumnValueLengthsToBeBetween: summary >= 30 ký tự.

    Returns:
        dict chứa kết quả validation (success, expectations, statistics).
    """
    # ── Khởi tạo GX 1.x ephemeral context ──
    context = gx.get_context(mode="ephemeral")

    # ── Đăng ký data source pandas ──
    data_source = context.data_sources.add_pandas(name="papers_source")
    data_asset = data_source.add_dataframe_asset(name="papers_asset")
    batch_def = data_asset.add_batch_definition_whole_dataframe("papers_batch")

    # ── Tạo Expectation Suite ──
    suite = context.suites.add(gx.ExpectationSuite(name="papers_quality_suite"))

    # Expectation 1: Số lượng bài báo hợp lệ (5 – 5000)
    suite.add_expectation(
        gxe.ExpectTableRowCountToBeBetween(min_value=5, max_value=5000)
    )

    # Expectation 2: Các cột bắt buộc không được null
    for col in ["paper_id", "title", "text_for_embedding"]:
        suite.add_expectation(
            gxe.ExpectColumnValuesToNotBeNull(column=col)
        )

    # Expectation 3: paper_id là khóa duy nhất
    suite.add_expectation(
        gxe.ExpectColumnValuesToBeUnique(column="paper_id")
    )

    # Expectation 4: summary có độ dài >= 30 ký tự
    suite.add_expectation(
        gxe.ExpectColumnValueLengthsToBeBetween(column="summary", min_value=30)
    )

    # ── Tạo Validation Definition và chạy ──
    validation_definition = context.validation_definitions.add(
        gx.ValidationDefinition(
            name="papers_validation",
            data=batch_def,
            suite=suite,
        )
    )

    # Chạy validation với batch parameters
    result = validation_definition.run(
        batch_parameters={"dataframe": df}
    )

    # ── Tổng hợp kết quả ──
    success = result.success

    expectations_results = []
    for exp_result in result.results:
        exp_config = exp_result.expectation_config
        exp_info = {
            "expectation_type": exp_config.type,
            "success": exp_result.success,
            "kwargs": {k: v for k, v in exp_config.kwargs.items() if k != "batch_id"},
        }
        if exp_result.result:
            exp_info["result"] = {
                k: v
                for k, v in exp_result.result.items()
                if k in ("observed_value", "element_count", "unexpected_count", "unexpected_percent")
            }
        expectations_results.append(exp_info)

    report = {
        "report_name": report_name,
        "success": success,
        "evaluated_expectations": len(expectations_results),
        "successful_expectations": sum(1 for e in expectations_results if e["success"]),
        "unsuccessful_expectations": sum(1 for e in expectations_results if not e["success"]),
        "expectations": expectations_results,
    }

    # ── Ghi report ──
    if report_name == "baseline":
        report_path = settings.paths.baseline_quality_report
    else:
        report_path = settings.paths.corrupted_quality_report
    write_json(report_path, report)

    status = "✅ PASSED" if success else "❌ FAILED"
    logger.info(
        "Data Quality Gate [%s]: %s (%d/%d expectations passed)",
        report_name,
        status,
        report["successful_expectations"],
        report["evaluated_expectations"],
    )

    return report


def build_freshness_report(
    df: pd.DataFrame,
    settings: Settings,
    report_path: Path | str | None = None,
) -> dict[str, Any]:
    """Kiểm tra độ tươi dữ liệu (Freshness SLA).

    Cảnh báo nếu tỉ lệ bài cũ (age_days > threshold) vượt quá 25%.

    Returns:
        dict chứa freshness metrics và is_fresh flag.
    """
    threshold = settings.freshness_threshold_days  # mặc định 180 ngày
    total_rows = len(df)
    target_path = Path(report_path) if report_path else settings.paths.freshness_report

    if total_rows == 0:
        report = {
            "latest_published": None,
            "oldest_published": None,
            "stale_rows": 0,
            "total_rows": 0,
            "stale_ratio": 0.0,
            "threshold_days": threshold,
            "max_stale_ratio": 0.25,
            "is_fresh": True,
            "sla_status": "PASSED (Empty)",
            "total_documents": 0,
            "stale_documents": 0,
            "fresh_documents": 0,
            "stale_threshold_days": threshold,
            "warning": "Không có dữ liệu để kiểm tra freshness.",
        }
        write_json(target_path, report)
        return report

    # ── Tính toán freshness ──
    latest_published = df["published"].max()
    oldest_published = df["published"].min()

    # Đếm bài cũ (age_days > threshold)
    stale_mask = df["age_days"] > threshold
    stale_rows = int(stale_mask.sum())
    stale_ratio = stale_rows / total_rows

    # Cảnh báo nếu > 25% bài cũ
    max_stale_ratio = 0.25
    is_fresh = stale_ratio <= max_stale_ratio

    report = {
        "latest_published": str(latest_published),
        "oldest_published": str(oldest_published),
        "stale_rows": stale_rows,
        "total_rows": total_rows,
        "stale_ratio": round(stale_ratio, 4),
        "threshold_days": threshold,
        "max_stale_ratio": max_stale_ratio,
        "is_fresh": is_fresh,
        "sla_status": "PASSED (Fresh)" if is_fresh else "WARNING (Stale)",
        "total_documents": total_rows,
        "stale_documents": stale_rows,
        "fresh_documents": total_rows - stale_rows,
        "stale_threshold_days": threshold,
    }

    if not is_fresh:
        report["warning"] = (
            f"⚠️ CẢNH BÁO: {stale_ratio:.1%} bài báo cũ hơn {threshold} ngày "
            f"(vượt ngưỡng {max_stale_ratio:.0%}). Cần cập nhật dữ liệu mới!"
        )
        logger.warning(report["warning"])
    else:
        logger.info(
            "✅ Freshness OK: %d/%d bài cũ (%.1f%% ≤ %.0f%%)",
            stale_rows,
            total_rows,
            stale_ratio * 100,
            max_stale_ratio * 100,
        )

    write_json(target_path, report)
    logger.info("📊 Freshness report → %s", target_path)

    return report

