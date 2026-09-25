from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import first_sentence, read_json, write_json

QUESTION_TYPES = ["summary", "authors", "date", "categories", "multi_hop"]
QUESTIONS_PER_TYPE = 2
REQUIRED_KEYS = {"id", "type", "question_type", "question", "ground_truth", "ground_truth_doc_ids"}


@dataclass(frozen=True)
class TestSet:
    samples: list[dict[str, Any]]
    path: Path

    def __len__(self) -> int:
        return len(self.samples)


def _pick_papers(df: pd.DataFrame, count: int) -> list[dict[str, Any]]:
    """Chon paper rai deu tu moi -> cu de test set phu ca bai moi nhat (bi drop khi corruption) lan bai cu."""
    # Title chua dau nhay don se lam hong regex `'<title>'` trong qa.answer_question.
    usable = df[~df["title"].str.contains("'", regex=False)]
    usable = usable.sort_values(["published", "paper_id"], ascending=[False, True]).reset_index(drop=True)
    if len(usable) < count:
        raise ValueError(f"Need at least {count} usable papers to build the test set, got {len(usable)}.")
    step = len(usable) / count
    return [usable.iloc[int(i * step)].to_dict() for i in range(count)]


def _single_paper_sample(question_type: str, paper: dict[str, Any]) -> dict[str, Any]:
    title = paper["title"]
    if question_type == "summary":
        question = f"What is the summary of the paper '{title}'?"
        ground_truth = first_sentence(paper["summary"])
    elif question_type == "authors":
        question = f"Who authored the paper '{title}'?"
        ground_truth = paper["authors_joined"]
    elif question_type == "date":
        question = f"When was the paper '{title}' published?"
        ground_truth = str(paper["published"])
    else:
        question = f"What categories does the paper '{title}' belong to?"
        ground_truth = paper["categories_joined"]
    return {"question": question, "ground_truth": ground_truth, "ground_truth_doc_ids": [paper["paper_id"]]}


def _multi_hop_sample(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    return {
        "question": (
            f"How do the paper '{first['title']}' ({first['primary_category']}) and the paper "
            f"'{second['title']}' ({second['primary_category']}) each contribute to their field?"
        ),
        "ground_truth": f"{first_sentence(first['summary'])} {first_sentence(second['summary'])}",
        "ground_truth_doc_ids": [first["paper_id"], second["paper_id"]],
    }


def _pair_across_categories(papers: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Ghep cap paper khac primary_category de cau multi_hop thuc su lien nganh."""
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    remaining = list(papers)
    while len(remaining) >= 2:
        first = remaining.pop(0)
        partner_index = next(
            (i for i, paper in enumerate(remaining) if paper["primary_category"] != first["primary_category"]),
            0,
        )
        pairs.append((first, remaining.pop(partner_index)))
    return pairs


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    single_types = [question_type for question_type in QUESTION_TYPES if question_type != "multi_hop"]
    paper_count = len(single_types) * QUESTIONS_PER_TYPE + 2 * QUESTIONS_PER_TYPE
    papers = _pick_papers(df, paper_count)

    drafts: list[tuple[str, dict[str, Any]]] = []
    cursor = 0
    for question_type in single_types:
        for paper in papers[cursor : cursor + QUESTIONS_PER_TYPE]:
            drafts.append((question_type, _single_paper_sample(question_type, paper)))
        cursor += QUESTIONS_PER_TYPE
    for first, second in _pair_across_categories(papers[cursor:]):
        drafts.append(("multi_hop", _multi_hop_sample(first, second)))

    samples = [
        {"id": f"eval_{index:03d}", "type": question_type, "question_type": question_type, **draft}
        for index, (question_type, draft) in enumerate(drafts, start=1)
    ]
    write_json(Path(output_path), samples)
    return samples


def load_or_create_test_set(df: pd.DataFrame, output_path, refresh: bool = False) -> TestSet:
    """Giu test set co dinh giua cac lan chay (baseline/corrupted/repaired phai cham cung mot de)."""
    path = Path(output_path)
    if path.exists() and not refresh:
        samples = read_json(path)
        if samples and all(REQUIRED_KEYS <= set(sample) for sample in samples):
            return TestSet(samples=samples, path=path)
    return TestSet(samples=build_test_set(df, path), path=path)
