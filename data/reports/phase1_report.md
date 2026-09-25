# Phase 1 Report - Baseline Pipeline

_Generated: 2026-09-25T08:59:07.350420+00:00_

## 1. Source & Lineage

- Source: Crossref REST API (offline snapshot)
- Query: `agentic retrieval augmented generation large language model`
- Filter: `from-pub-date:2026-03-29,has-abstract:true`
- Raw records: 24 -> clean rows: 24 (dropped 0)
- Embedding: `sentence-transformers/all-MiniLM-L6-v2` -> Chroma collection `papers-baseline` (top_k=4)
- LLM (judge / agent): `gemini / gemini-3.5-flash`

## 2. Data Quality Gate (Great Expectations 1.x)

- Engine: `great_expectations 1.18.0` (ephemeral context)
- Gate status: **PASS** (0/6 expectations failed, 24 rows)

| Expectation | Column | Status | Observed | Unexpected |
|---|---|---|---|---|
| expect_table_row_count_to_be_between | - | PASS | 24 | - |
| expect_column_values_to_not_be_null | paper_id | PASS | - | 0 |
| expect_column_values_to_be_unique | paper_id | PASS | - | 0 |
| expect_column_values_to_not_be_null | title | PASS | - | 0 |
| expect_column_values_to_not_be_null | text_for_embedding | PASS | - | 0 |
| expect_column_value_lengths_to_be_between | summary | PASS | - | 0 |

## 3. Freshness SLA

| Latest published | Oldest published | Stale rows | Stale ratio | SLA | Status |
|---|---|---|---|---|---|
| 2026-07-22 | 2026-03-28 | 1/24 | 4.2% | <= 25% older than 180 days | FRESH |

## 4. Baseline Evaluation

| Samples | Retrieval hit rate | Mean token F1 | Judge accuracy | Mean judge score (1-5) |
|---|---|---|---|---|
| 10 | 1.00 | 0.95 | 1.00 | 4.60 |

> Note: LLM judge unavailable for 7/10 answers; those were scored with the token-F1 heuristic fallback.

**Breakdown by question type**

| Question type | Samples | Hit rate | Token F1 | Judge accuracy |
|---|---|---|---|---|
| summary | 2 | 1.00 | 1.00 | 1.00 |
| authors | 2 | 1.00 | 1.00 | 1.00 |
| date | 2 | 1.00 | 1.00 | 1.00 |
| categories | 2 | 1.00 | 1.00 | 1.00 |
| multi_hop | 2 | 1.00 | 0.73 | 1.00 |

**Ragas**: skipped=Set RUN_RAGAS=1 to enable the slower Ragas pass.

## 5. Agent Demo

- **Q (eval_001)**: What is the summary of the paper 'Continuous Benchmark Evaluation for Enterprise Retrieval Pipelines'?
  - Agent: Agent call failed: Error calling model 'gemini-3.5-flash' (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash\nPlease retry in 10.771849318s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-3.5-flash'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '10s'}]}}
  - Ground truth: Static benchmarks fail to capture domain drift in enterprise knowledge bases.
- **Q (eval_002)**: What is the summary of the paper 'Freshness SLAs for Real-Time LLM Knowledge Augmentation'?
  - Agent: Agent call failed: Error calling model 'gemini-3.5-flash' (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash\nPlease retry in 10.237897755s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-3.5-flash'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '10s'}]}}
  - Ground truth: We define freshness service-level agreements (SLAs) for temporal document ingestion.
