from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import html
from pathlib import Path
import re
import time
from typing import Any

import requests

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json

CROSSREF_WORKS_URL = "https://api.crossref.org/works"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 30
DOI_PREFIX_PATTERN = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", re.IGNORECASE)
JATS_TITLE_PATTERN = re.compile(r"<jats:title[^>]*>.*?</jats:title>", re.IGNORECASE | re.DOTALL)
TAG_PATTERN = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def normalize_doi(value: str) -> str:
    return DOI_PREFIX_PATTERN.sub("", (value or "").strip()).strip()


def strip_markup(value: str) -> str:
    """Bo cac the JATS/HTML (vd `<jats:p>`) va heading "Abstract" ma Crossref chen vao abstract."""
    without_headings = JATS_TITLE_PATTERN.sub(" ", value or "")
    without_tags = TAG_PATTERN.sub(" ", without_headings)
    return normalize_whitespace(html.unescape(without_tags))


def _first_text(value: Any) -> str:
    if isinstance(value, list):
        value = next((item for item in value if item), "")
    return normalize_whitespace(str(value or ""))


def _date_from_parts(field: dict[str, Any] | None) -> str:
    """Crossref `date-parts` co the chi co [nam] hoac [nam, thang] -> dien ngay/thang mac dinh la 1."""
    if not field:
        return ""
    parts = (field.get("date-parts") or [[]])[0] or []
    if not parts or parts[0] is None:
        return ""
    year, month, day = (list(parts) + [1, 1])[:3]
    return datetime(int(year), int(month), int(day)).date().isoformat()


def _date_from_datetime(field: dict[str, Any] | None) -> str:
    if not field or not field.get("date-time"):
        return ""
    return datetime.fromisoformat(field["date-time"].replace("Z", "+00:00")).date().isoformat()


def _parse_authors(raw_authors: list[dict[str, Any]] | None) -> list[str]:
    authors: list[str] = []
    for author in raw_authors or []:
        name = normalize_whitespace(" ".join(part for part in (author.get("given"), author.get("family")) if part))
        name = name or normalize_whitespace(author.get("name", ""))
        if name:
            authors.append(name)
    return authors


def _pdf_url(item: dict[str, Any], fallback: str) -> str:
    for link in item.get("link") or []:
        if link.get("content-type") == "application/pdf" and link.get("URL"):
            return link["URL"]
    return fallback


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    records: list[PaperRecord] = []
    for item in payload.get("message", {}).get("items", []):
        paper_id = normalize_doi(item.get("DOI", ""))
        title = _first_text(item.get("title"))
        summary = strip_markup(item.get("abstract", ""))
        published = (
            _date_from_parts(item.get("published"))
            or _date_from_parts(item.get("published-online"))
            or _date_from_parts(item.get("published-print"))
            or _date_from_parts(item.get("issued"))
            or _date_from_datetime(item.get("created"))
        )
        if not (paper_id and title and summary and published):
            continue

        updated = (
            _date_from_datetime(item.get("updated"))
            or _date_from_datetime(item.get("indexed"))
            or _date_from_datetime(item.get("created"))
            or published
        )
        categories = [normalize_whitespace(subject) for subject in item.get("subject") or [] if subject]
        abs_url = item.get("URL") or f"https://doi.org/{paper_id}"
        records.append(
            PaperRecord(
                paper_id=paper_id,
                title=title,
                summary=summary,
                authors=_parse_authors(item.get("author")),
                categories=categories,
                primary_category=categories[0] if categories else "Uncategorized",
                published=published,
                updated=updated,
                abs_url=abs_url,
                pdf_url=_pdf_url(item, abs_url),
                comment=f"Crossref record {paper_id}",
            )
        )
    return records


def _request_crossref(settings: Settings) -> dict[str, Any]:
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
        "sort": "published",
        "order": "desc",
    }
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(CROSSREF_WORKS_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException as error:
            last_error = error
        else:
            if response.status_code == 200:
                return response.json()
            last_error = RuntimeError(f"Crossref API returned HTTP {response.status_code}")
            if response.status_code not in RETRYABLE_STATUS_CODES:
                break
        if attempt < MAX_ATTEMPTS:
            time.sleep(2**attempt)
    raise RuntimeError(f"Crossref API unavailable after {MAX_ATTEMPTS} attempts") from last_error


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Dual-mode: goi Crossref API khi REFRESH_SOURCE=1, fallback ve snapshot offline khi loi/mat mang.

    Snapshot `raw_api_response` chi bi ghi de khi API tra ve payload hop le, nen ban goc luon con de repair.
    """
    snapshot_path = settings.paths.raw_api_response
    payload: dict[str, Any] | None = None

    if settings.refresh_source or not snapshot_path.exists():
        try:
            payload = _request_crossref(settings)
        except RuntimeError as error:
            if not snapshot_path.exists():
                raise
            print(f"[crossref] {error}; fallback to offline snapshot {snapshot_path}")

    if payload is None:
        payload = read_json(snapshot_path)
        records = parse_crossref_payload(payload)
    else:
        records = parse_crossref_payload(payload)
        if not records:
            raise RuntimeError("Crossref API returned no usable records; keeping existing snapshot.")
        write_json(snapshot_path, payload)

    write_json(settings.paths.raw_records_json, [asdict(record) for record in records])
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    return [
        PaperRecord(
            paper_id=str(row.get("paper_id", "")),
            title=str(row.get("title", "")),
            summary=str(row.get("summary", "")),
            authors=list(row.get("authors") or []),
            categories=list(row.get("categories") or []),
            primary_category=str(row.get("primary_category", "")),
            published=str(row.get("published", "")),
            updated=str(row.get("updated", "")),
            abs_url=str(row.get("abs_url", "")),
            pdf_url=str(row.get("pdf_url", "")),
            comment=str(row.get("comment", "")),
        )
        for row in read_json(path)
    ]
