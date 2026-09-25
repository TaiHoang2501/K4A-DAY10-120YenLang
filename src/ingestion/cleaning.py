from __future__ import annotations

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
