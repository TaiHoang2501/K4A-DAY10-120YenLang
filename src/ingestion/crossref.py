import html
import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from core.config import Settings

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

    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Đọc JSON snapshot đã bóc tách và map thành list PaperRecord."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [PaperRecord(**item) for item in data]
