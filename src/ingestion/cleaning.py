from __future__ import annotations

from datetime import UTC, datetime
import logging

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord

logger = logging.getLogger(__name__)


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
    return pd.DataFrame(
        columns=[
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
    )

