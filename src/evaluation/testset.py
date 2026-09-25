from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import first_sentence, read_json, write_json


class TestSet(list):
    """Wrapper cho test set benchmark, vừa tương thích list vừa hỗ trợ thuộc tính .samples."""

    def __init__(self, samples: list[dict[str, Any]] | None = None):
        super().__init__(samples or [])
        self.samples = list(self)


def load_or_create_test_set(
    df: pd.DataFrame,
    output_path: str | Path,
    force_refresh: bool = False,
) -> TestSet:
    """Tải test set nếu file đã tồn tại, hoặc sinh mới nếu chưa có hoặc khi force_refresh=True."""
    output_path = Path(output_path)
    if output_path.exists() and not force_refresh:
        try:
            items = read_json(output_path)
            if isinstance(items, list) and len(items) > 0:
                return TestSet(items)
        except Exception:
            pass
    return build_test_set(df, output_path)


def build_test_set(df: pd.DataFrame, output_path: str | Path) -> TestSet:
    """Xây dựng bộ benchmark test set gồm 10 câu hỏi chia đều vào 5 dạng bài toán:
    - summary: Tóm tắt nội dung nghiên cứu chính.
    - authors: Ai là tác giả của nghiên cứu về chủ đề X?
    - date: Nghiên cứu Y được công bố vào năm/tháng nào?
    - category: Công trình này thuộc lĩnh vực chuyên môn nào?
    - multi_hop: Câu hỏi kết hợp liên ngành giữa hai chủ đề.

    Mỗi mẫu bắt buộc có: id, type, question, ground_truth, ground_truth_doc_ids.
    """
    if df.empty or len(df) < 5:
        raise ValueError("Cleaned dataframe must contain at least 5 records to build benchmark test set.")

    output_path = Path(output_path)

    # Chọn các bài báo đại diện từ dataframe
    p0 = df.iloc[0]
    p1 = df.iloc[1]
    p2 = df.iloc[2]
    p3 = df.iloc[3]
    p4 = df.iloc[4]

    def _get_authors(row: pd.Series) -> str:
        if "authors_joined" in row and pd.notna(row["authors_joined"]) and row["authors_joined"]:
            return str(row["authors_joined"])
        authors = row.get("authors", [])
        if isinstance(authors, list):
            return ", ".join(str(a) for a in authors)
        return str(authors)

    def _get_categories(row: pd.Series) -> str:
        if "categories_joined" in row and pd.notna(row["categories_joined"]) and row["categories_joined"]:
            return str(row["categories_joined"])
        cats = row.get("categories", [])
        if isinstance(cats, list):
            return ", ".join(str(c) for c in cats)
        return str(cats)

    def _get_date(row: pd.Series) -> str:
        val = row.get("published", "")
        if pd.isna(val):
            return ""
        if hasattr(val, "strftime"):
            return val.strftime("%Y-%m-%d")
        return str(val).split("T")[0]

    test_items = [
        # 1. Summary: Tóm tắt nội dung nghiên cứu chính
        {
            "id": "eval_001",
            "type": "summary",
            "question_type": "summary",
            "question": f"What is the summary of the paper '{p0['title']}'?",
            "ground_truth": first_sentence(str(p0["summary"])),
            "ground_truth_doc_ids": [str(p0["paper_id"])],
        },
        {
            "id": "eval_002",
            "type": "summary",
            "question_type": "summary",
            "question": f"What is the summary of the paper '{p1['title']}'?",
            "ground_truth": first_sentence(str(p1["summary"])),
            "ground_truth_doc_ids": [str(p1["paper_id"])],
        },
        # 2. Authors: Ai là tác giả của nghiên cứu về chủ đề X?
        {
            "id": "eval_003",
            "type": "authors",
            "question_type": "authors",
            "question": f"Who authored the paper '{p2['title']}'?",
            "ground_truth": _get_authors(p2),
            "ground_truth_doc_ids": [str(p2["paper_id"])],
        },
        {
            "id": "eval_004",
            "type": "authors",
            "question_type": "authors",
            "question": f"Who authored the paper '{p3['title']}'?",
            "ground_truth": _get_authors(p3),
            "ground_truth_doc_ids": [str(p3["paper_id"])],
        },
        # 3. Date: Nghiên cứu Y được công bố vào năm/tháng nào?
        {
            "id": "eval_005",
            "type": "date",
            "question_type": "date",
            "question": f"When was the paper '{p4['title']}' published?",
            "ground_truth": _get_date(p4),
            "ground_truth_doc_ids": [str(p4["paper_id"])],
        },
        {
            "id": "eval_006",
            "type": "date",
            "question_type": "date",
            "question": f"When was the paper '{p0['title']}' published?",
            "ground_truth": _get_date(p0),
            "ground_truth_doc_ids": [str(p0["paper_id"])],
        },
        # 4. Category: Công trình này thuộc lĩnh vực chuyên môn nào?
        {
            "id": "eval_007",
            "type": "category",
            "question_type": "category",
            "question": f"What categories does the paper '{p1['title']}' belong to?",
            "ground_truth": _get_categories(p1),
            "ground_truth_doc_ids": [str(p1["paper_id"])],
        },
        {
            "id": "eval_008",
            "type": "category",
            "question_type": "category",
            "question": f"What categories does the paper '{p4['title']}' belong to?",
            "ground_truth": _get_categories(p4),
            "ground_truth_doc_ids": [str(p4["paper_id"])],
        },
        # 5. Multi-hop: Câu hỏi kết hợp liên ngành giữa hai chủ đề
        {
            "id": "eval_009",
            "type": "multi_hop",
            "question_type": "multi_hop",
            "question": f"What is the summary of the paper '{p1['title']}' in relation to '{p4['title']}'?",
            "ground_truth": first_sentence(str(p1["summary"])),
            "ground_truth_doc_ids": [str(p1["paper_id"]), str(p4["paper_id"])],
        },
        {
            "id": "eval_010",
            "type": "multi_hop",
            "question_type": "multi_hop",
            "question": f"What is the summary of the paper '{p3['title']}' in relation to '{p0['title']}'?",
            "ground_truth": first_sentence(str(p3["summary"])),
            "ground_truth_doc_ids": [str(p3["paper_id"]), str(p0["paper_id"])],
        },
    ]

    write_json(output_path, test_items)
    return TestSet(test_items)

