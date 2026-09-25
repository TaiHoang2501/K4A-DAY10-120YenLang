from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from ingestion.crossref import PaperRecord, load_raw_records

if TYPE_CHECKING:
    from core.config import Settings

logger = logging.getLogger(__name__)


def _normalize_spaces(text: str | None) -> str:
    """Chuẩn hóa khoảng trắng thừa."""
    if not text:
        return ""
    return " ".join(str(text).split()).strip()


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Làm sạch raw records thành DataFrame sẵn sàng để embed và đánh chỉ mục vector.

    Quy trình:
    1. Chuẩn hóa title, summary, authors, categories.
    2. Parse published/updated date, tính toán age_days = (run_date - published).days.
    3. Tạo các cột tiện ích:
       - authors_joined: chuỗi các tác giả ghép bởi dấu phẩy.
       - categories_joined: chuỗi các chuyên ngành ghép bởi dấu phẩy.
       - summary_chars: độ dài ký tự của summary.
       - text_for_embedding: cấu trúc ngữ cảnh 5 phần phục vụ MiniLM embedding.
    4. Khử trùng lặp theo paper_id và lọc các dòng thiếu khóa chính/tiêu đề.
    5. Sắp xếp nhất quán (deterministic sort) và reset index.
    """
    if not records:
        return pd.DataFrame()

    run_d = run_date.date() if isinstance(run_date, datetime) else run_date

    rows = []
    for r in records:
        paper_id = _normalize_spaces(r.paper_id)
        if not paper_id:
            continue

        title = _normalize_spaces(r.title)
        if not title:
            continue

        summary = _normalize_spaces(r.summary)

        clean_authors = [_normalize_spaces(a) for a in r.authors if _normalize_spaces(a)]
        authors_joined = ", ".join(clean_authors)

        clean_categories = [_normalize_spaces(c) for c in r.categories if _normalize_spaces(c)]
        categories_joined = ", ".join(clean_categories)
        primary_category = _normalize_spaces(r.primary_category) or (
            clean_categories[0] if clean_categories else "General"
        )

        published_str = str(r.published).strip()
        try:
            pub_date = datetime.strptime(published_str[:10], "%Y-%m-%d").date()
            age_days = (run_d - pub_date).days
        except Exception:
            age_days = 0

        updated_str = str(r.updated).strip() if r.updated else published_str
        summary_chars = len(summary)

        # Cấu trúc chuẩn 5 phần theo Guide.md
        text_for_embedding = (
            f"Title: {title}\n"
            f"Authors: {authors_joined}\n"
            f"Published: {published_str}\n"
            f"Categories: {categories_joined}\n"
            f"Summary: {summary}"
        )

        rows.append(
            {
                "paper_id": paper_id,
                "title": title,
                "summary": summary,
                "authors": clean_authors,
                "authors_joined": authors_joined,
                "categories": clean_categories,
                "categories_joined": categories_joined,
                "primary_category": primary_category,
                "published": published_str,
                "updated": updated_str,
                "age_days": age_days,
                "summary_chars": summary_chars,
                "abs_url": str(r.abs_url).strip(),
                "pdf_url": str(r.pdf_url).strip(),
                "comment": str(r.comment).strip(),
                "text_for_embedding": text_for_embedding,
            }
        )

    df = pd.DataFrame(rows)

    # Khử trùng lặp theo paper_id, giữ bản ghi đầu tiên
    df = df.drop_duplicates(subset=["paper_id"], keep="first")

    # Sắp xếp nhất quán theo published giảm dần và paper_id tăng dần để đảm bảo tính Idempotent
    df = df.sort_values(by=["published", "paper_id"], ascending=[False, True]).reset_index(drop=True)

    return df


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

    effective_date = run_date or datetime.now(timezone.utc)
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

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from core.utils import compact_join, ensure_parent, normalize_whitespace, write_csv
from ingestion.crossref import PaperRecord, strip_markup

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
    "age_days",
    "authors_joined",
    "categories_joined",
    "summary_chars",
    "text_for_embedding",
]


def build_text_for_embedding(row: pd.Series) -> str:
    return "\n".join(
        [
            f"Title: {row['title']}",
            f"Authors: {row['authors_joined']}",
            f"Published: {row['published']}",
            f"Categories: {row['categories_joined']}",
            f"Summary: {row['summary']}",
        ]
    )


def _clean_list(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    for value in values or []:
        item = normalize_whitespace(str(value))
        if item and item not in cleaned:
            cleaned.append(item)
    return cleaned


def _iso_date(value: str) -> str:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    return "" if pd.isna(parsed) else parsed.date().isoformat()


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=CLEAN_COLUMNS)

    df = pd.DataFrame([asdict(record) for record in records])

    df["paper_id"] = df["paper_id"].fillna("").map(lambda value: normalize_whitespace(str(value)))
    df["title"] = df["title"].fillna("").map(lambda value: normalize_whitespace(str(value)))
    df["summary"] = df["summary"].fillna("").map(lambda value: strip_markup(str(value)))
    df["authors"] = df["authors"].map(_clean_list)
    df["categories"] = df["categories"].map(_clean_list)
    df["primary_category"] = [
        normalize_whitespace(str(primary)) or (categories[0] if categories else "Uncategorized")
        for primary, categories in zip(df["primary_category"].fillna(""), df["categories"], strict=True)
    ]

    df["published"] = df["published"].fillna("").map(_iso_date)
    df["updated"] = df["updated"].fillna("").map(_iso_date)
    df["updated"] = df["updated"].where(df["updated"] != "", df["published"])

    run_date = run_date if run_date.tzinfo else run_date.replace(tzinfo=UTC)
    published_at = pd.to_datetime(df["published"], errors="coerce", utc=True)
    df["age_days"] = (pd.Timestamp(run_date) - published_at).dt.days

    df = df[(df["paper_id"] != "") & (df["title"] != "") & (df["summary"] != "") & df["age_days"].notna()]
    # Giu ban cap nhat moi nhat khi cung mot paper_id xuat hien nhieu lan.
    df = df.sort_values(["updated", "published"], ascending=False)
    df = df.drop_duplicates(subset="paper_id", keep="first").copy()

    df["age_days"] = df["age_days"].astype(int)
    df["authors_joined"] = df["authors"].map(compact_join)
    df["categories_joined"] = df["categories"].map(compact_join)
    df["summary_chars"] = df["summary"].str.len()
    df["text_for_embedding"] = df.apply(build_text_for_embedding, axis=1)

    df = df.sort_values(["published", "paper_id"], ascending=[False, True]).reset_index(drop=True)
    return df[CLEAN_COLUMNS]


def save_clean_dataframe(df: pd.DataFrame, csv_path: Path, json_path: Path) -> None:
    write_csv(df, csv_path)
    ensure_parent(json_path)
    df.to_json(json_path, orient="records", indent=2, force_ascii=False)
