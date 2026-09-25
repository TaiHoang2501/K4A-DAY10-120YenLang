# Corruption Report - Baseline vs Corrupted vs Repaired

_Generated: 2026-09-25T09:11:52.303145+00:00_

## 1. Headline Metrics

| Metric | Baseline | Corrupted | Repaired | Corrupted vs Baseline | Repaired vs Baseline |
|---|---|---|---|---|---|
| Retrieval hit rate | 1.00 | 0.70 | 1.00 | -0.30 | +0.00 |
| Mean token F1 | 0.95 | 0.84 | 0.95 | -0.10 | +0.00 |
| Judge accuracy | 1.00 | 0.70 | 0.90 | -0.30 | -0.10 |
| Mean judge score (1-5) | 4.60 | 3.90 | 4.60 | -0.70 | +0.00 |

> Judge answers scored by the heuristic fallback (LLM unavailable): Baseline 7/10, Corrupted 0/10, Repaired 3/10.

**Token F1 / hit rate by question type**

| Question type | Baseline | Corrupted | Repaired |
|---|---|---|---|
| summary | 1.00 / 1.00 | 0.65 / 0.00 | 1.00 / 1.00 |
| authors | 1.00 / 1.00 | 1.00 / 0.50 | 1.00 / 1.00 |
| date | 1.00 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 |
| categories | 1.00 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 |
| multi_hop | 0.73 / 1.00 | 0.57 / 1.00 | 0.73 / 1.00 |

## 2. Injected Corruption

Seed `42`: 24 rows -> 22 rows, 6 scenarios.

| # | Scenario | Rows | Description |
|---|---|---|---|
| 1 | drop_latest_records | 5 | Dropped the 5 most recently published papers (20%). |
| 2 | blank_summary | 3 | Replaced the summary with an empty string. |
| 3 | inject_text_noise | 3 | Inserted random garbage tokens into the summary / text_for_embedding. |
| 4 | truncate_title | 3 | Truncated the title to 7 characters. |
| 5 | stale_date | 7 | Moved the publication date back 5 years. |
| 6 | duplicate_rows | 3 | Appended exact copies of existing rows. |

## 3. Data Quality Gate (Great Expectations 1.x)

| Expectation | Column | Corrupted | Repaired |
|---|---|---|---|
| expect_table_row_count_to_be_between | - | PASS (22) | PASS |
| expect_column_values_to_not_be_null | paper_id | PASS (0) | PASS |
| expect_column_values_to_be_unique | paper_id | FAIL (6) | PASS |
| expect_column_values_to_not_be_null | title | PASS (0) | PASS |
| expect_column_values_to_not_be_null | text_for_embedding | PASS (0) | PASS |
| expect_column_value_lengths_to_be_between | summary | FAIL (4) | PASS |

- Gate status: corrupted **FAIL**, repaired **PASS**

## 4. Freshness SLA

| State | Latest published | Oldest published | Stale rows | Stale ratio | Status |
|---|---|---|---|---|---|
| Corrupted | 2026-06-12 | 2021-03-28 | 8/22 | 36.4% | STALE |
| Repaired | 2026-07-22 | 2026-03-28 | 1/24 | 4.2% | FRESH |

## 5. Repair

- Rebuilt 24 rows from the trusted raw snapshot `crossref_records.json` with the same cleaning code (no patching of the corrupted table).
- Content identical to baseline (ignoring run-date dependent `age_days`): **True**

## 6. Conclusion

- Corruption dropped retrieval hit rate by 0.30 and token F1 by 0.10; the RAG pipeline still returned fluent answers (silent failure) - only the quality gate and freshness SLA flagged the problem.
- Repair restored hit rate to 1.00 and token F1 to 0.95.
