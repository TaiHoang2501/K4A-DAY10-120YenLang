from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import requests

from core.config import Settings
from core.utils import normalize_whitespace, write_json

logger = logging.getLogger(__name__)

# ---------- Regex để loại bỏ JATS / HTML tags ----------
_TAG_RE = re.compile(r"<[^>]+>")


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


# ── Helpers ──────────────────────────────────────────────


def _strip_tags(text: str) -> str:
    """Loại bỏ tất cả thẻ HTML/JATS XML (vd: <jats:p>, </jats:p>, <b>)."""
    return _TAG_RE.sub("", text)


def _parse_date_parts(date_obj: dict | None) -> str:
    """Chuyển đổi Crossref date-parts [[2026, 5, 20]] → '2026-05-20' (ISO 8601).

    Nếu thiếu tháng/ngày sẽ mặc định là 01.
    """
    if not date_obj:
        return ""
    parts = date_obj.get("date-parts", [[]])[0]
    if not parts:
        return ""
    year = parts[0]
    month = parts[1] if len(parts) > 1 else 1
    day = parts[2] if len(parts) > 2 else 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def _format_authors(author_list: list[dict]) -> list[str]:
    """Ghép 'given' + 'family' thành tên đầy đủ, bỏ qua author thiếu tên."""
    authors: list[str] = []
    for a in author_list:
        given = a.get("given", "").strip()
        family = a.get("family", "").strip()
        full = normalize_whitespace(f"{given} {family}")
        if full:
            authors.append(full)
    return authors


# ── Core parsing ─────────────────────────────────────────


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse Crossref API JSON payload thành list[PaperRecord].

    Quy tắc:
    1. Duyệt ``payload["message"]["items"]``.
    2. Chuẩn hóa DOI (lowercase, strip), title (normalize whitespace),
       abstract (loại bỏ JATS/HTML tags rồi normalize whitespace).
    3. Bỏ qua record thiếu DOI hoặc thiếu cả title lẫn abstract.
    4. Trả về list ``PaperRecord``.
    """
    items = payload.get("message", {}).get("items", [])
    records: list[PaperRecord] = []

    for item in items:
        # --- paper_id: DOI chuẩn hóa ---
        doi = (item.get("DOI") or "").strip().lower()
        if not doi:
            logger.warning("Bỏ qua item không có DOI")
            continue

        # --- title ---
        raw_titles = item.get("title", [])
        title = normalize_whitespace(raw_titles[0]) if raw_titles else ""

        # --- summary (abstract): loại bỏ JATS/HTML tags ---
        raw_abstract = item.get("abstract", "")
        summary = normalize_whitespace(_strip_tags(raw_abstract))

        # Bỏ record thiếu cả title lẫn summary
        if not title and not summary:
            logger.warning("Bỏ qua DOI %s: thiếu cả title lẫn abstract", doi)
            continue

        # --- authors ---
        authors = _format_authors(item.get("author", []))

        # --- categories (subject) ---
        categories = [s.strip() for s in item.get("subject", []) if s.strip()]
        primary_category = categories[0] if categories else ""

        # --- published / updated (ISO 8601) ---
        published = _parse_date_parts(item.get("published"))
        # Crossref không luôn có 'updated', fallback về created hoặc published
        updated = (
            _parse_date_parts(item.get("updated"))
            or item.get("created", {}).get("date-time", "")[:10]
            or published
        )

        # --- URLs ---
        abs_url = item.get("URL", f"https://doi.org/{doi}")
        pdf_url = abs_url  # Crossref không cung cấp PDF trực tiếp

        records.append(
            PaperRecord(
                paper_id=doi,
                title=title,
                summary=summary,
                authors=authors,
                categories=categories,
                primary_category=primary_category,
                published=published,
                updated=updated,
                abs_url=abs_url,
                pdf_url=pdf_url,
                comment=f"Crossref record {doi}",
            )
        )

    logger.info("Đã parse %d/%d records hợp lệ từ Crossref payload", len(records), len(items))
    return records


# ── Fetching với Dual-Mode (Online / Offline fallback) ───


_CROSSREF_API = "https://api.crossref.org/works"
_MAX_RETRIES = 3


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Gọi Crossref REST API, lưu raw response, parse thành records.

    **Cơ chế Dual-Mode:**
    - Nếu ``settings.refresh_source`` là True → gọi API trực tiếp.
    - Nếu API trả về 429 (Too Many Requests), 503 hoặc mất mạng →
      tự động fallback sang snapshot offline tại
      ``settings.paths.raw_api_response`` (data/raw/crossref_response.json).
    - Nếu ``settings.refresh_source`` là False → đọc thẳng snapshot offline.
    """
    snapshot_path = settings.paths.raw_api_response

    # ── Chế độ Offline (mặc định) ──
    if not settings.refresh_source:
        logger.info("🟢 Chế độ Offline: Đọc snapshot từ %s", snapshot_path)
        return _parse_and_save(snapshot_path, settings)

    # ── Chế độ Live API ──
    logger.info("🌐 Chế độ Live API: Gọi Crossref REST API …")
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
    }

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.get(
                _CROSSREF_API,
                params=params,
                headers={"User-Agent": "DataObservabilityLab/1.0 (student lab)"},
                timeout=30,
            )

            if resp.status_code == 200:
                payload = resp.json()
                # Lưu raw response
                write_json(snapshot_path, payload)
                logger.info("✅ API thành công. Đã lưu raw response → %s", snapshot_path)
                return _parse_and_save(snapshot_path, settings, payload=payload)

            if resp.status_code in {429, 503}:
                logger.warning(
                    "⚠️ API trả về %d (attempt %d/%d). Chuyển sang Offline.",
                    resp.status_code,
                    attempt,
                    _MAX_RETRIES,
                )
                # Fallback ngay, không cần retry thêm cho 429
                break

            logger.warning("API lỗi %d (attempt %d/%d)", resp.status_code, attempt, _MAX_RETRIES)

        except requests.RequestException as exc:
            logger.warning("🔌 Mất kết nối (attempt %d/%d): %s", attempt, _MAX_RETRIES, exc)

    # ── Fallback sang Offline snapshot ──
    logger.info("🔄 Fallback Offline: Đọc snapshot từ %s", snapshot_path)
    if not snapshot_path.exists():
        raise FileNotFoundError(
            f"Không thể gọi API và không tìm thấy snapshot offline tại {snapshot_path}"
        )
    return _parse_and_save(snapshot_path, settings)


def _parse_and_save(
    snapshot_path: Path,
    settings: Settings,
    payload: dict | None = None,
) -> list[PaperRecord]:
    """Đọc payload (hoặc load từ file), parse và lưu records JSON."""
    if payload is None:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

    records = parse_crossref_payload(payload)

    # Lưu records đã parse ra file JSON
    records_dicts = [asdict(r) for r in records]
    write_json(settings.paths.raw_records_json, records_dicts)
    logger.info("💾 Đã lưu %d records → %s", len(records), settings.paths.raw_records_json)

    return records


# ── Load từ snapshot đã parse sẵn ────────────────────────


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Đọc JSON snapshot (crossref_records.json) và map thành list[PaperRecord]."""
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy file records tại {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    records: list[PaperRecord] = []
    for item in raw:
        records.append(
            PaperRecord(
                paper_id=item["paper_id"],
                title=item.get("title", ""),
                summary=item.get("summary", ""),
                authors=item.get("authors", []),
                categories=item.get("categories", []),
                primary_category=item.get("primary_category", ""),
                published=item.get("published", ""),
                updated=item.get("updated", ""),
                abs_url=item.get("abs_url", ""),
                pdf_url=item.get("pdf_url", ""),
                comment=item.get("comment", ""),
            )
        )

    logger.info("📂 Đã load %d records từ %s", len(records), path)
    return records
