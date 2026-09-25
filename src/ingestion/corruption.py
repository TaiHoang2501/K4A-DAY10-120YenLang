from __future__ import annotations

from pathlib import Path
import random
from typing import Any

import pandas as pd

from core.utils import compact_join, now_utc, write_json
from ingestion.cleaning import CLEAN_COLUMNS, build_text_for_embedding

DEFAULT_SEED = 42
DROP_LATEST_RATIO = 0.20
BLANK_SUMMARY_ROWS = 3
NOISE_ROWS = 3
TRUNCATE_TITLE_ROWS = 3
TRUNCATED_TITLE_CHARS = 7
# > 25% de vuot Freshness SLA (MAX_STALE_RATIO) ke ca khi da cong them dong duplicate.
STALE_RATIO = 0.35
STALE_YEARS = 5
DUPLICATE_ROWS = 3
NOISE_ALPHABET = "#@$%&*~^!?<>{}[]|0123456789xqzjkw"


def _noise_token(rng: random.Random) -> str:
    return "".join(rng.choice(NOISE_ALPHABET) for _ in range(rng.randint(6, 12)))


def _inject_noise(text: str, rng: random.Random) -> str:
    """Chen token rac vao giua cac tu -> van con chu goc nhung embedding bi lech huong."""
    words = text.split()
    for _ in range(max(4, len(words) // 3)):
        words.insert(rng.randint(0, len(words)), _noise_token(rng))
    return " ".join(words)


def _step(name: str, description: str, rows: pd.DataFrame, **details: Any) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "affected_rows": int(len(rows)),
        "paper_ids": rows["paper_id"].tolist(),
        **details,
    }


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path, seed: int = DEFAULT_SEED) -> pd.DataFrame:
    rng = random.Random(seed)
    corrupted = df.copy().reset_index(drop=True)
    corrupted["published"] = corrupted["published"].astype(str)
    steps: list[dict[str, Any]] = []

    # 1. Drop latest records: mat 20% bai moi nhat.
    drop_count = max(1, round(len(corrupted) * DROP_LATEST_RATIO))
    latest = corrupted.sort_values(["published", "paper_id"], ascending=[False, True]).head(drop_count)
    steps.append(
        _step(
            "drop_latest_records",
            f"Dropped the {drop_count} most recently published papers ({DROP_LATEST_RATIO:.0%}).",
            latest,
            published=latest["published"].tolist(),
        )
    )
    corrupted = corrupted.drop(index=latest.index).reset_index(drop=True)

    # Cac buoc 2-5 dung tap dong rieng biet de log ro dong nao bi loi gi.
    order = list(corrupted.index)
    rng.shuffle(order)
    stale_count = max(1, round(len(corrupted) * STALE_RATIO))
    cursor = 0

    def take(count: int) -> list[int]:
        nonlocal cursor
        picked = sorted(order[cursor : cursor + count])
        cursor += count
        return picked

    # 2. Blank summary.
    rows = take(BLANK_SUMMARY_ROWS)
    steps.append(_step("blank_summary", "Replaced the summary with an empty string.", corrupted.loc[rows]))
    corrupted.loc[rows, "summary"] = ""

    # 3. Inject text noise vao summary (lan sang text_for_embedding khi rebuild o buoc 7).
    rows = take(NOISE_ROWS)
    steps.append(
        _step("inject_text_noise", "Inserted random garbage tokens into the summary / text_for_embedding.", corrupted.loc[rows])
    )
    for row in rows:
        corrupted.at[row, "summary"] = _inject_noise(corrupted.at[row, "summary"], rng)

    # 4. Truncate title.
    rows = take(TRUNCATE_TITLE_ROWS)
    original_titles = corrupted.loc[rows, "title"].tolist()
    corrupted.loc[rows, "title"] = corrupted.loc[rows, "title"].str[:TRUNCATED_TITLE_CHARS]
    steps.append(
        _step(
            "truncate_title",
            f"Truncated the title to {TRUNCATED_TITLE_CHARS} characters.",
            corrupted.loc[rows],
            original_titles=original_titles,
            truncated_titles=corrupted.loc[rows, "title"].tolist(),
        )
    )

    # 5. Stale date: lui ngay xuat ban ve 5 nam truoc.
    rows = take(stale_count)
    original_dates = corrupted.loc[rows, "published"].tolist()
    old_published = pd.to_datetime(corrupted.loc[rows, "published"])
    new_published = old_published - pd.DateOffset(years=STALE_YEARS)
    corrupted.loc[rows, "published"] = new_published.dt.date.astype(str)
    corrupted.loc[rows, "age_days"] = corrupted.loc[rows, "age_days"] + (old_published - new_published).dt.days
    steps.append(
        _step(
            "stale_date",
            f"Moved the publication date back {STALE_YEARS} years.",
            corrupted.loc[rows],
            original_published=original_dates,
            corrupted_published=corrupted.loc[rows, "published"].tolist(),
        )
    )

    # 6. Duplicate rows.
    rows = sorted(rng.sample(list(corrupted.index), DUPLICATE_ROWS))
    steps.append(_step("duplicate_rows", "Appended exact copies of existing rows.", corrupted.loc[rows]))
    corrupted = pd.concat([corrupted, corrupted.loc[rows]], ignore_index=True)

    # 7. Rebuild cac cot dan xuat de loi lan vao embedding.
    corrupted["authors_joined"] = corrupted["authors"].map(compact_join)
    corrupted["categories_joined"] = corrupted["categories"].map(compact_join)
    corrupted["summary_chars"] = corrupted["summary"].str.len()
    corrupted["text_for_embedding"] = corrupted.apply(build_text_for_embedding, axis=1)
    corrupted = corrupted[CLEAN_COLUMNS]

    # 8. Ghi corruption log.
    for number, step in enumerate(steps, start=1):
        step["step"] = number
    write_json(
        Path(output_log_path),
        {
            "generated_at": now_utc().isoformat(),
            "seed": seed,
            "input_rows": int(len(df)),
            "output_rows": int(len(corrupted)),
            "scenarios": len(steps),
            "steps": steps,
        },
    )
    return corrupted
