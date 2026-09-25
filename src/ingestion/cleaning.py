from __future__ import annotations

from datetime import UTC, datetime
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord, load_raw_records

if TYPE_CHECKING:
    from core.config import Settings

logger = logging.getLogger(__name__)

CLEAN_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors",
    "categories",
    "primary_category",
    "published",
    "updated",
    "abs_url",
    "pdf_url",
    "comment",
    "authors_joined",
    "categories_joined",
    "summary_chars",
    "age_days",
    "text_for_embedding",
]


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime | None = None) -> pd.DataFrame:
    """Chuyển đổi raw records thành DataFrame sạch, sẵn sàng để embedding.

    Pipeline xử lý:
    1. Normalize title, summary, authors, categories.
    2. Parse published/updated → datetime, tính ``age_days``.
    3. Tạo các cột helper: ``authors_joined``, ``categories_joined``,
       ``summary_chars``, ``text_for_embedding``.
    4. Khử trùng lặp theo ``paper_id`` (giữ bản ghi mới nhất).
    5. Loại bỏ bản ghi xấu (thiếu cả title lẫn summary).
    6. Sort theo ``published`` giảm dần và reset index.
    """
    if run_date is None:
        run_date = datetime.now(UTC)

    if not records:
        logger.warning("Không có records nào để làm sạch")
        return _empty_dataframe()

    rows: list[dict] = []
    for rec in records:
        # ── Normalize text fields ──
        title = normalize_whitespace(rec.title)
        summary = normalize_whitespace(rec.summary)
        authors = [normalize_whitespace(a) for a in rec.authors if a.strip()]
        categories = [normalize_whitespace(c) for c in rec.categories if c.strip()]

        # ── Joined strings ──
        authors_joined = compact_join(authors, ", ")
        categories_joined = compact_join(categories, ", ")

        # ── Parse dates ──
        published_dt = _safe_parse_date(rec.published)
        updated_dt = _safe_parse_date(rec.updated) or published_dt

        # ── Tính age_days = (run_date - published).days ──
        age_days = (run_date.date() - published_dt.date()).days if published_dt else None

        # ── summary_chars ──
        summary_chars = len(summary)

        # ── text_for_embedding: nội dung tổng hợp cho Vector DB ──
        text_for_embedding = (
            f"Title: {title}\n"
            f"Authors: {authors_joined}\n"
            f"Published: {rec.published}\n"
            f"Categories: {categories_joined}\n"
            f"Summary: {summary}"
        )

        rows.append(
            {
                "paper_id": rec.paper_id,
                "title": title,
                "summary": summary,
                "authors": authors,
                "categories": categories,
                "primary_category": rec.primary_category,
                "published": rec.published,
                "updated": rec.updated,
                "abs_url": rec.abs_url,
                "pdf_url": rec.pdf_url,
                "comment": rec.comment,
                "authors_joined": authors_joined,
                "categories_joined": categories_joined,
                "summary_chars": summary_chars,
                "age_days": age_days,
                "text_for_embedding": text_for_embedding,
            }
        )

    df = pd.DataFrame(rows)

    n_before = len(df)

    # ── Khử trùng lặp theo paper_id (giữ bản ghi đầu tiên — mới nhất) ──
    df = df.drop_duplicates(subset=["paper_id"], keep="first")
    n_deduped = n_before - len(df)
    if n_deduped > 0:
        logger.info("🔁 Đã loại bỏ %d bản ghi trùng lặp", n_deduped)

    # ── Loại bỏ bản ghi xấu: thiếu cả title lẫn summary ──
    mask_bad = (df["title"].str.strip() == "") & (df["summary"].str.strip() == "")
    n_bad = mask_bad.sum()
    if n_bad > 0:
        logger.warning("🗑️ Loại bỏ %d bản ghi thiếu cả title lẫn summary", n_bad)
        df = df[~mask_bad]

    # ── Sort theo published giảm dần (mới nhất lên đầu) ──
    df = df.sort_values("published", ascending=False).reset_index(drop=True)

    logger.info(
        "✅ Cleaning hoàn tất: %d records (bỏ %d trùng, %d xấu)",
        len(df),
        n_deduped,
        n_bad,
    )
    return df


# ── Helpers ──────────────────────────────────────────────


def _safe_parse_date(date_str: str) -> datetime | None:
    """Parse chuỗi ngày ISO 8601 (YYYY-MM-DD) an toàn, trả None nếu lỗi."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _empty_dataframe() -> pd.DataFrame:
    """Trả về DataFrame rỗng với đúng schema."""
    return pd.DataFrame(columns=CLEAN_COLUMNS)


def build_text_for_embedding(row: pd.Series) -> str:
    """Ghép lại text_for_embedding từ một dòng (dùng khi corruption.py sửa title/summary/published)."""
    return (
        f"Title: {row['title']}\n"
        f"Authors: {row['authors_joined']}\n"
        f"Published: {row['published']}\n"
        f"Categories: {row['categories_joined']}\n"
        f"Summary: {row['summary']}"
    )


def save_clean_dataframe(
    df: pd.DataFrame, csv_path: Path, json_path: Path | None = None
) -> None:
    """Lưu dataframe sạch ra file CSV và JSON (nếu có chỉ định)."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False, encoding="utf-8")
    if json_path:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_json(json_path, orient="records", indent=2, force_ascii=False)


def repair_clean_dataset(
    settings: Settings, run_date: datetime | None = None
) -> pd.DataFrame:
    """Tái tạo dữ liệu sạch trực tiếp từ kho raw snapshot (Idempotent Repair).

    Đọc lại từ file snapshot thô `data/raw/crossref_records.json` (hoặc fallback API),
    chạy qua quy trình làm sạch chuẩn build_clean_dataframe()
    và lưu đồng nhất vào cả clean artifacts và repaired artifacts.
    Chạy lại bao nhiêu lần vẫn tạo ra cùng một kết quả chuẩn sạch.
    """
    raw_path = settings.paths.raw_records_json
    if not raw_path.exists():
        from ingestion.crossref import fetch_source_records

        records = fetch_source_records(settings)
    else:
        records = load_raw_records(raw_path)

    effective_date = run_date or datetime.now(UTC)
    clean_df = build_clean_dataframe(records, run_date=effective_date)

    # Lưu vào kho clean chuẩn
    save_clean_dataframe(
        clean_df,
        csv_path=settings.paths.clean_csv,
        json_path=settings.paths.clean_json,
    )
    # Lưu vào kho repaired artifacts
    save_clean_dataframe(
        clean_df,
        csv_path=settings.paths.repaired_clean_csv,
        json_path=settings.paths.repaired_clean_json,
    )

    logger.info("Idempotent repair hoàn tất: %d bản ghi đã được tái tạo sạch.", len(clean_df))
    return clean_df

