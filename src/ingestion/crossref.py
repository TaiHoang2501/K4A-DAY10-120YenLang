import html
import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
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

logger = logging.getLogger(__name__)


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


def _clean_text(text: str | None) -> str:
    """Loại bỏ thẻ HTML/XML rác, unescape entities và chuẩn hóa khoảng trắng."""
    if not text:
        return ""
    # Loại bỏ các thẻ HTML / JATS XML như <jats:p>, </jats:p>, <i>, <b>...
    cleaned = re.sub(r"<[^>]+>", " ", str(text))
    # Unescape HTML entities (ví dụ: &amp;, &lt;, &gt;)
    cleaned = html.unescape(cleaned)
    # Chuẩn hóa khoảng trắng thừa
    return " ".join(cleaned.split()).strip()


def _extract_iso_date(date_data: Any, fallback_date: str = "2026-01-01") -> str:
    """Parse ngày tháng từ định dạng Crossref thành chuỗi ISO 8601 YYYY-MM-DD."""
    if isinstance(date_data, dict):
        date_parts = date_data.get("date-parts")
        if date_parts and isinstance(date_parts, list) and len(date_parts) > 0:
            parts = date_parts[0]
            if isinstance(parts, list) and parts:
                year = int(parts[0]) if len(parts) >= 1 else 2026
                month = int(parts[1]) if len(parts) >= 2 else 1
                day = int(parts[2]) if len(parts) >= 3 else 1
                return f"{year:04d}-{month:02d}-{day:02d}"
        date_time = date_data.get("date-time")
        if date_time and isinstance(date_time, str):
            return date_time.split("T")[0].strip()
    elif isinstance(date_data, str):
        cleaned = date_data.split("T")[0].strip()
        if len(cleaned) >= 10:
            return cleaned[:10]
        if cleaned:
            return cleaned
    return fallback_date


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse Crossref payload thành danh sách PaperRecord chuẩn hóa.

    Bóc tách các trường:
    - paper_id: DOI chuẩn hóa.
    - title: Chuẩn hóa khoảng trắng.
    - summary: Loại bỏ các thẻ HTML/JATS XML rác (<jats:p>, </jats:p>...).
    - authors: Danh sách tên tác giả đã ghép chuẩn hóa.
    - categories & primary_category: Chuyên ngành nghiên cứu.
    - published & updated: Định dạng ngày ISO 8601 (YYYY-MM-DD).
    - abs_url, pdf_url, comment: Các metadata liên kết.
    """
    items = (
        payload.get("message", {}).get("items", [])
        if "message" in payload
        else payload.get("items", [])
    )
    records: list[PaperRecord] = []

    for item in items:
        doi = str(item.get("DOI", "")).strip()
        if not doi:
            continue

        raw_title = item.get("title", "")
        if isinstance(raw_title, list):
            raw_title = raw_title[0] if raw_title else ""
        title = _clean_text(str(raw_title))

        raw_abstract = item.get("abstract", "") or item.get("summary", "") or ""
        summary = _clean_text(str(raw_abstract))

        authors: list[str] = []
        for a in item.get("author", []):
            if isinstance(a, dict):
                given = str(a.get("given", "")).strip()
                family = str(a.get("family", "")).strip()
                name = f"{given} {family}".strip() if (given or family) else str(a.get("name", "")).strip()
                if name:
                    authors.append(" ".join(name.split()))
            elif isinstance(a, str) and a.strip():
                authors.append(" ".join(a.strip().split()))

        categories = [
            " ".join(str(s).split())
            for s in item.get("subject", [])
            if str(s).strip()
        ]
        primary_category = categories[0] if categories else "General"

        published = _extract_iso_date(item.get("published"), fallback_date="2026-01-01")
        updated = _extract_iso_date(item.get("updated"), fallback_date=published)

        url = str(item.get("URL", "")).strip() or f"https://doi.org/{doi}"

        record = PaperRecord(
            paper_id=doi,
            title=title,
            summary=summary,
            authors=authors,
            categories=categories,
            primary_category=primary_category,
            published=published,
            updated=updated,
            abs_url=url,
            pdf_url=url,
            comment=f"Crossref record {doi}",
        )
        records.append(record)

    return records


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Gọi Crossref REST API hoặc nạp snapshot local fallback, lưu raw artifacts và parse."""
    raw_response_path = settings.paths.raw_api_response
    raw_records_path = settings.paths.raw_records_json

    payload: dict | None = None

    # Nếu được cấu hình refresh_source=True, thử kết nối tới Crossref API
    if settings.refresh_source:
        try:
            params = {
                "query": settings.source_query,
                "filter": settings.source_filter,
                "rows": settings.max_results,
            }
            headers = {
                "User-Agent": "Day10-RAG-Observability-Lab/1.0 (mailto:lab@vinuni.edu.vn)"
            }
            resp = requests.get(
                "https://api.crossref.org/works",
                params=params,
                headers=headers,
                timeout=15,
            )
            if resp.status_code == 200:
                payload = resp.json()
                raw_response_path.parent.mkdir(parents=True, exist_ok=True)
                with open(raw_response_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
            else:
                logger.warning(
                    "Crossref API returned HTTP %s. Falling back to local raw snapshot.",
                    resp.status_code,
                )
        except Exception as exc:
            logger.warning(
                "Failed to fetch from Crossref API (%s). Falling back to local snapshot.",
                exc,
            )

    # Chế độ Dev/Offline fallback: Đọc từ raw snapshot đã lưu sẵn
    if payload is None:
        if raw_response_path.exists():
            with open(raw_response_path, encoding="utf-8") as f:
                payload = json.load(f)
        elif raw_records_path.exists():
            return load_raw_records(raw_records_path)
        else:
            raise FileNotFoundError(
                f"Cannot find raw API response at {raw_response_path} or records at {raw_records_path}"
            )

    records = parse_crossref_payload(payload)

    # Lưu lại danh sách records vào raw_records_json để bảo toàn lineage
    raw_records_path.parent.mkdir(parents=True, exist_ok=True)
    with open(raw_records_path, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in records], f, indent=2, ensure_ascii=False)

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
    """Đọc JSON snapshot đã bóc tách và map thành list PaperRecord."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [PaperRecord(**item) for item in data]
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
