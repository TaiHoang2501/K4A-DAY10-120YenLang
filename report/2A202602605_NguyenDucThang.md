# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Nguyễn Đức Thắng             |
| MSSV               | 2A202602605                     |
| Khóa/Lớp         | K4              |
| Tên nhóm         | 120YenLang     |
| Vai trò chính    | Pipeline Lead (điều phối & tích hợp pipeline) |
| Repository         | https://github.com/TaiHoang2501/K4A-DAY10-120YenLang |
| Ngày hoàn thành | 2026-09-25               |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao  | Trạng thái                                 |
| ------------------ | --------------------- | ---------------- | ----------------- | -------------------------------------------- |
| Pipeline Pha 1 (baseline) | `src/pipelines/phase1.py` — `main()` | `Settings`, raw snapshot, module của các thành viên 2–5 | `papers_clean.csv/json`, collection `papers-baseline`, `test_set.json`, `baseline_metrics.json`, `agent_demo_answers.json`, `phase1_report.md` | Hoàn thành. Bản hiện tại trên `main` đến từ nhánh RAG qua PR #5; tôi tích hợp để nó chạy được với các module sau merge |
| Pipeline corruption → repair → compare | `src/pipelines/corruption_flow.py` — `main()`, `_evaluate_state()`, `_check_quality()`, `_matches_baseline()` | Artifact baseline, `crossref_records.json` | `corrupted_*`, `repaired_*` (clean/embeddings/metrics/answers), collection `papers-corrupted` / `papers-repaired`, `corruption_report.md` | Hoàn thành |
| Cấu hình & contract đường dẫn | `src/core/config.py` — field `paths.test_set_json` (sửa lỗi trùng với `@property` sau merge) | Hướng dẫn lab | Đường dẫn artifact thống nhất cho mọi module | Hoàn thành |
| Tích hợp sau merge PR #5 | `ingestion/cleaning.py` (`save_clean_dataframe`, `repair_clean_dataset`, `CLEAN_COLUMNS`, `build_text_for_embedding`), `observability/quality.py` (tên file report), `observability/reporting.py` (key `expectation_type`), `corruption_flow.py` | Code 9 file bị thay nguyên trong PR #5 | Cả 2 pipeline chạy lại EXIT=0 | Hoàn thành |
| Entry point | `script/run_phase1.py`, `script/run_corruption_flow.py` | — | Hai lệnh chạy end-to-end | Hoàn thành (dùng sẵn, gọi `main()`) |

Phần việc của tôi nằm ở giữa: nhận output của Data Foundation (thành viên 2: `build_clean_dataframe`, `load_raw_records`), đưa qua quality gate của Observability (thành viên 4), index bằng module của RAG Specialist (thành viên 3), rồi giao cho Evaluation & Reporting (thành viên 5) chấm điểm và xuất báo cáo.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                         | Thành viên/module được hỗ trợ | Kết quả                    |
| ------------------------------------ | ------------------------------------ | ---------------------------- |
| Debug pipeline treo ở bước evaluate | RAG Specialist — `retrieval/llm.py` | Thêm `timeout` (45 giây) + `max_retries` (1) cho mọi LLM client, chỉnh bằng env `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`; `run_phase1.py` chạy hết với EXIT=0 |
| Debug treo khi load embedding model | RAG Specialist — `retrieval/embeddings.py` | Load MiniLM từ cache local (`local_files_only=True`), chỉ lên mạng khi chưa có cache |
| Chốt contract giữa các module | Evaluation & Reporting — `evaluation/metrics.py`, `observability/reporting.py` | Thống nhất thêm `by_question_type`, `judge_fallback_count` vào metrics (vẫn còn trong code hiện tại) |
| Khôi phục code Data Foundation bị ghi đè | Data Foundation — `ingestion/cleaning.py` | Lấy lại `save_clean_dataframe`, `repair_clean_dataset` từ commit `137c799` của Trần Anh Quân, để `ingestion/__init__.py` import được |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao       | Cách xác minh         |
| --------------------------- | ----------------------------- | ------------------------- | ----------------------- |
| Chạy Pha 1 end-to-end 7 bước (+ demo 2 câu) | `src/pipelines/phase1.py` | 5 artifact bắt buộc của CP3 | `python script/run_phase1.py` → log `[1/7] … [7/7]`, `Hoàn tất thành công!`, EXIT=0 |
| Giữ test set cố định giữa các lần chạy, chỉ sinh lại khi `REFRESH_TEST_SET=1` | `phase1.py` gọi `load_or_create_test_set(..., force_refresh=settings.refresh_test_set)` | `data/eval/test_set.json` (10 câu) dùng chung cho 3 trạng thái | Chạy lại pipeline → SHA-256 file không đổi (`c3772946d68d`) |
| Sửa lỗi import sau merge PR #5 | `core/config.py`, `ingestion/cleaning.py`, `pipelines/corruption_flow.py` | Mọi package import được | `import core, ingestion, observability, evaluation, retrieval, pipelines` → OK |
| Nối luồng corruption → evaluate → repair → compare | `src/pipelines/corruption_flow.py` | Bảng 3 trạng thái trên console + `corruption_report.md` | `python script/run_corruption_flow.py` → EXIT=0 |
| Kiểm tra repair có idempotent (trùng khớp baseline) | `corruption_flow.py` — `_matches_baseline()` | `identical to baseline=True` | Log `[corruption] Repaired: 24 rows rebuilt from raw, identical to baseline=True` |
| Tách 3 Chroma collection để so sánh độc lập | `corruption_flow.py` — `_evaluate_state()` gọi `LocalEmbeddingIndex.build(df, settings, embeddings_path)` | `papers-baseline`, `papers-corrupted`, `papers-repaired` | `data/embeddings/papers_embeddings*.json` ghi đúng `collection_name` |

Output cụ thể phần việc của tôi tạo ra:

Bảng đối chiếu trong `data/reports/corruption_report.md` và trên console khi chạy `run_corruption_flow.py`: retrieval hit rate 1.00 → 0.00 → 1.00, token F1 1.00 → 0.51 → 1.00, judge accuracy 1.00 → 0.60 → 1.00. Quality gate corrupted FAIL (2/6 expectation), repaired PASS (0/6). Dữ liệu repaired trùng khớp baseline (`matches_baseline=True`).

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Mỗi thành viên viết một module riêng: lấy dữ liệu, làm sạch, quality gate, index, test set, chấm điểm, báo cáo. Nếu không có ai nối lại thì không có lệnh nào chạy được từ đầu đến cuối, và không có cách lặp lại thí nghiệm "dữ liệu bẩn làm RAG sai mà không báo lỗi". Vai trò của tôi là biến các module đó thành hai pipeline chạy được bằng một lệnh, có thứ tự đúng, có điểm dừng khi dữ liệu xấu, và cho kết quả lặp lại được.

### Cách triển khai

**Pha 1 (`phase1.py`, bản hiện tại trên `main`)** chạy tuần tự:

1. `fetch_source_records`: mặc định đọc snapshot offline, đặt `REFRESH_SOURCE=1` thì gọi API.
2. `build_clean_dataframe(records, run_date=settings.run_date)`, lưu CSV/JSON.
3. `run_data_quality_checks(..., phase_label="baseline")` + `build_freshness_report`, in `Quality Check Status` và `Freshness SLA Status`. Bản này **chưa dừng** khi gate FAIL: dữ liệu bẩn vẫn được index, đây là điểm cần bổ sung.
4. `LocalEmbeddingIndex.build` → collection `papers-baseline`.
5. `load_or_create_test_set(..., force_refresh=settings.refresh_test_set)`: dùng lại test set đã có, chỉ sinh lại khi `REFRESH_TEST_SET=1`.
6. `evaluate_pipeline` → `baseline_metrics.json`, `baseline_answers.json`.
7. `generate_phase1_report` → `phase1_report.md`.
8. Demo 2 câu hỏi mẫu bằng `answer_question` → `agent_demo_answers.json`.

Phiên bản `phase1.py` tôi viết trước merge có dừng pipeline khi gate FAIL và chạy demo bằng LangChain agent. PR #5 đã thay nó bằng bản trên; tôi giữ bản trên `main` và chỉ sửa các module xung quanh để nó chạy được.

**Corruption flow (`corruption_flow.py`):**

1. Kiểm tra đủ artifact baseline, thiếu thì báo chạy Pha 1 trước.
2. `corrupt_clean_dataframe` (seed 42) → lưu `papers_clean_corrupted.*`.
3. Quality gate trên dữ liệu bẩn. Ở đây tôi cố ý **không dừng** khi FAIL mà in cảnh báo "production would stop here" rồi vẫn index, vì mục tiêu của lab là đo mức thiệt hại.
4. Index `papers-corrupted` và đánh giá bằng **cùng** `test_set.json`.
5. Repair: đọc lại `crossref_records.json` và chạy lại đúng hàm `build_clean_dataframe`. Gate phải PASS, nếu không thì `raise`.
6. `_matches_baseline` so sánh 7 cột nội dung (bỏ `age_days` vì cột này phụ thuộc ngày chạy).
7. Index `papers-repaired`, đánh giá, in bảng 3 trạng thái, gọi `generate_corruption_report`.

### Input, output và contract

| Thành phần                   | Mô tả                                     |
| ------------------------------ | ------------------------------------------- |
| Input                          | `Settings` (`load_settings()`, đọc `.env`); `data/raw/crossref_response.json` / `crossref_records.json`; biến env `REFRESH_SOURCE`, `REFRESH_TEST_SET`, `LLM_PROVIDER`, `LLM_MODEL` |
| Output                         | Pha 1: `data/clean/papers_clean.*`, `data/quality/baseline_quality_report.json`, `freshness_report.json`, `data/eval/test_set.json`, `data/results/baseline_{metrics,answers}.json`, `agent_demo_answers.json`, `data/reports/phase1_report.md`. Corruption flow: `corruption_log.json`, `*_corrupted.*`, `*_repaired.*`, `{corrupted,repaired}_{quality,freshness}_report.json`, `data/reports/corruption_report.md` |
| Module phụ thuộc             | `ingestion.crossref`, `ingestion.cleaning`, `ingestion.corruption`, `observability.quality`, `observability.reporting`, `retrieval.index`, `retrieval.qa`, `evaluation.testset`, `evaluation.metrics` |
| Module sử dụng output        | `script/run_phase1.py`, `script/run_corruption_flow.py`; corruption flow dùng output của Pha 1 (`clean_json`, `baseline_metrics.json`, `test_set.json`) |
| Điều kiện lỗi cần xử lý | Quality gate repaired FAIL → `corruption_flow.py` dừng (`raise`); thiếu artifact baseline → báo chạy Pha 1 trước; LLM timeout/429 → judge dùng heuristic (đếm trong `judge_fallback_count`); API Crossref lỗi → fallback snapshot. **Chưa xử lý:** gate baseline FAIL không dừng Pha 1 |

### Cách xác minh

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** Cả hai lệnh chạy xong. Pha 1 sinh đủ 5 artifact của CP3. Corruption flow cho thấy chỉ số giảm ở trạng thái corrupted và phục hồi ở trạng thái repaired.
- **Kết quả thực tế:**
  - `run_phase1.py` (lần chạy 2026-09-25 10:10:43Z, ~22 giây): EXIT=0, log `Quality Check Status: True (6/6 expectations)`, `Freshness SLA Status: PASSED (Fresh)`, `Retrieval Hit Rate: 100.00%`, `Mean Token F1: 1.0000`.
  - `run_corruption_flow.py` (10:11:05Z → 10:11:37Z): EXIT=0, gate corrupted FAIL (`expect_column_values_to_be_unique(paper_id)`, `expect_column_value_lengths_to_be_between(summary)`), `is_fresh=False (8/22 stale)`; repaired PASS, `identical to baseline=True`; bảng 3 trạng thái ở mục 8.
- **Artifact/log:** `data/reports/phase1_report.md`, `data/reports/corruption_report.md`, `data/results/*.json`, `data/quality/*.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Sau khi tiêm lỗi, cần đưa dữ liệu về trạng thái sạch để chứng minh pipeline phục hồi được. Có hai cách repair.
- **Các phương án đã cân nhắc:**
  1. **Vá bảng bị hỏng:** `drop_duplicates`, bỏ dòng summary rỗng, lọc token rác bằng regex. Cách này giữ được 22 dòng còn lại.
  2. **Dựng lại từ raw snapshot:** đọc `crossref_records.json` (nguồn tin cậy, không bị động tới) và chạy lại đúng code làm sạch như baseline.
- **Phương án đã chọn:** (2) dựng lại từ raw.
- **Lý do:**
  - Cách (1) không khôi phục được dữ liệu đã **mất**: 5 bài mới nhất bị bỏ, tiêu đề bị cắt, ngày bị lùi 5 năm. Vá chỉ che triệu chứng.
  - Cách (1) cần một quy tắc sửa riêng cho từng loại lỗi. Mỗi loại lỗi mới lại cần thêm code, và khó biết đã sửa hết chưa.
  - Cách (2) idempotent: chạy bao nhiêu lần cũng ra cùng kết quả, và dùng chung một đường code với baseline nên không có hai logic làm sạch khác nhau.
  - Trade-off: cách (2) phụ thuộc raw snapshot còn nguyên. Vì vậy snapshot chỉ bị ghi đè khi API trả về payload hợp lệ (phần của Data Foundation).
- **Bằng chứng quyết định phù hợp:**
  - `_matches_baseline` trả về `True`: 24 dòng repaired trùng khớp baseline trên 7 cột nội dung.
  - Hit rate, token F1, judge accuracy về lại 1.00 / 1.00 / 1.00, **đúng bằng** baseline.
  - Quality gate repaired PASS 6/6; freshness 1/24 stale (4.2%).

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** `python script/run_phase1.py` chạy xong bước 1–5 trong vài giây, sau đó đứng im hơn 10 phút ở bước evaluate, không log, không lỗi, không tiến thêm. Xảy ra 2 lần liên tiếp.
- **Lệnh hoặc bước tái hiện:** Chạy vòng lặp `answer_question` + `_judge_answer` trên 10 câu của `test_set.json`, bật `faulthandler.dump_traceback_later(300)` để dump stack trace khi treo.
- **Nguyên nhân gốc:** Có hai lời gọi mạng không có timeout:
  1. `SentenceTransformer(model_name)` gửi một loạt HEAD request lên `huggingface.co` mỗi lần load model, dù model đã có trong cache. Một request bị treo là cả process treo theo. (Khi đặt `HF_HUB_OFFLINE=1`: load + embed + search chỉ mất dưới 1 giây.)
  2. Client Gemini (`ChatGoogleGenerativeAI`) được tạo không có `timeout`. Stack trace dừng ở `ssl.py … read` ← `httpcore … _receive_response_headers` ← `google/genai/_api_client.py … _request_once` ← `evaluation/metrics.py line 63 in _judge_answer`, tức là đang chờ header phản hồi từ Gemini vô thời hạn.

  Thêm một yếu tố gây nhiễu khi debug: trên Windows, dừng tác vụ nền (kill bash) **không** kill process python con. Hai process pipeline cũ vẫn chạy và dùng chung Chroma. Tôi phải liệt kê process (`Get-CimInstance Win32_Process`) và kill thủ công.
- **Cách xử lý:**
  - `retrieval/embeddings.py`: thử `SentenceTransformer(model_name, local_files_only=True)` trước, bắt `OSError` thì mới tải online.
  - `retrieval/llm.py`: thêm `timeout=LLM_TIMEOUT_SECONDS` (mặc định 45) và `max_retries=LLM_MAX_RETRIES` (mặc định 1) cho mọi provider. Ollama nhận timeout qua `client_kwargs`.
  - Khi LLM lỗi, `_judge_answer` đã có sẵn heuristic fallback. Tôi thêm `judge_fallback_count` vào metrics để báo cáo ghi rõ có bao nhiêu câu phải chấm bằng heuristic.
- **Cách xác minh sau khi sửa:**
  - Load model với log `httpx` bật: không còn request nào tới huggingface.co.
  - `run_phase1.py` chạy hết 7/7 với EXIT=0.
  - Log cho thấy nguyên nhân thứ ba: API key Gemini dùng gói miễn phí, giới hạn 20 request/ngày/model (`429 RESOURCE_EXHAUSTED … limit: 20, model: gemini-3.5-flash`). Pipeline không còn treo mà chuyển sang heuristic (7/10 câu).
- **Điều học được:** Mọi lời gọi mạng trong batch pipeline đều phải có timeout và giới hạn retry. Một request treo không báo lỗi còn tệ hơn một request lỗi, vì nó chặn mọi bước phía sau. Khi pipeline "đứng im", dump stack trace (`faulthandler`) nhanh hơn nhiều so với đoán mò.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. **Từ Crossref đến vector index:**
   - `crossref.py` lấy payload (API hoặc snapshot offline), giữ nguyên bản gốc ở `crossref_response.json`, parse thành `PaperRecord` và lưu `crossref_records.json`.
   - `cleaning.py` chuẩn hóa text, bỏ thẻ JATS, tính `age_days`, khử trùng lặp theo `paper_id` và ghép `text_for_embedding` (Title/Authors/Published/Categories/Summary).
   - Quality gate GX phải PASS thì mới đi tiếp.
   - `LocalEmbeddingIndex.build` embed `text_for_embedding` bằng `all-MiniLM-L6-v2` (vector chuẩn hóa, cosine) và ghi vào collection Chroma, kèm metadata (tác giả, ngày, chuyên ngành, summary) để QA trích câu trả lời.
2. **Evaluation set:** mỗi câu hỏi có `ground_truth` (đáp án) và `ground_truth_doc_ids` (DOI của bài chứa đáp án).
   - Retrieval hit = trong top-k tài liệu lấy về có ít nhất một DOI đúng. Chỉ số này đo phần *tìm kiếm*.
   - Token F1 so sánh câu trả lời với `ground_truth`, còn LLM judge chấm mức đúng về nghĩa. Hai chỉ số này đo phần *trả lời*.
   - Tách hai lớp đo giúp thấy lỗi mà một lớp bỏ sót. Ví dụ ở trạng thái corrupted: `eval_007` (category) có F1 = 1.00 và judge chấm đúng, nhưng retrieval hit = False. Bài đúng đã bị bỏ, câu trả lời lấy từ một bài khác tình cờ cùng chuyên ngành. Chỉ lớp retrieval cho thấy lỗi.
3. **Quality checks vs freshness:**
   - Quality checks (GX) kiểm tra *tính hợp lệ của từng dòng/cột*: số dòng, not-null, unique `paper_id`, độ dài summary. Kết quả là PASS/FAIL; FAIL ở bảng repaired làm dừng corruption flow (Pha 1 hiện mới chỉ in trạng thái).
   - Freshness kiểm tra *tuổi của cả tập dữ liệu*: tỉ lệ bài có `age_days > 180` phải ≤ 25%. Đây là tín hiệu cảnh báo (`is_fresh`), không làm dừng pipeline.
   - Lỗi `stale_date` qua được mọi expectation GX, và chỉ freshness bắt được (8/22 = 36.4% → STALE).
4. **Cùng test set cho 3 trạng thái:** để biến duy nhất thay đổi là dữ liệu. Nếu mỗi trạng thái sinh test set riêng từ chính dữ liệu của nó (vd. từ bảng corrupted, vốn đã mất 5 bài mới nhất), câu hỏi sẽ tự né phần dữ liệu bị mất và chỉ số sẽ không giảm. Cách đó che đi đúng lỗi cần đo. Vì vậy `load_or_create_test_set` giữ file cố định và corruption flow luôn đọc `paths.eval_testset` do Pha 1 tạo.
5. **Repair thành công dựa trên:**
   - `repaired_quality_report.json` PASS 6/6.
   - `repaired_freshness_report.json` `is_fresh=true` (1/24).
   - `matches_baseline=True` (nội dung trùng khớp baseline).
   - `repaired_metrics.json` có hit rate 1.00, token F1 1.00, judge accuracy 1.00, bằng baseline. Lần chạy này cả 3 trạng thái đều do Gemini chấm (0/10 câu heuristic) nên judge accuracy so sánh được.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal          | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ---------------------- | -------: | --------: | -------: | ------------------------- |
| `retrieval_hit_rate` |     1.00 |      0.00 |     1.00 | Cả 10 câu hỏi về 5 bài mới nhất (`testset.py` sinh từ `df.iloc[0..4]`), đúng 5 bài bị `drop_latest_records` bỏ |
| `mean_token_f1`      |     1.00 |      0.51 |     1.00 | Không về 0 vì câu trả lời từ bài khác vẫn trùng một phần token. Theo dạng: date 0.00, multi_hop 0.36, authors 0.50, summary 0.70, category 1.00 |
| `judge_accuracy`     |     1.00 |      0.60 |     1.00 | Cả 3 trạng thái đều do Gemini chấm (0/10 heuristic) nên so sánh được. Nhưng judge vẫn chấm đúng 5/5 hai câu chứa chuỗi rác (`eval_002`, `eval_009`), nên 0.60 là cao hơn thực tế |
| `mean_judge_score`   |     5.00 |      3.40 |     5.00 | Cùng lưu ý như `judge_accuracy` |
| Quality checks         | PASS (0/6 fail) | FAIL (2/6 fail) | PASS (0/6 fail) | Corrupted: `paper_id` không unique (6 dòng), summary < 30 ký tự (4 dòng) |
| Freshness status       | FRESH (1/24 = 4.2%) | STALE (8/22 = 36.4%) | FRESH (1/24 = 4.2%) | `stale_date` lùi 7 bài về 5 năm trước, vượt ngưỡng 25% |

Số liệu từ lần chạy 2026-09-25 10:10–10:11Z trên code đã merge của `main`. Chạy lại cho kết quả giống hệt, vì snapshot và seed cố định.

### Kết luận từ số liệu

1. Tiêm 6 loại lỗi (bỏ 5 bài mới nhất, xóa 3 summary, chèn rác vào 3 summary, cắt 3 tiêu đề, lùi ngày 7 bài, nhân đôi 3 dòng) → quality gate FAIL (unique `paper_id`, độ dài summary) và freshness STALE (36.4%) → hit rate 1.00 → 0.00, token F1 1.00 → 0.51, judge accuracy 1.00 → 0.60. RAG vẫn trả lời trơn tru, không báo lỗi gì (silent failure).
2. Dựng lại từ `crossref_records.json` bằng cùng code làm sạch → gate PASS 6/6, freshness FRESH (4.2%), nội dung trùng khớp baseline → cả 4 chỉ số phục hồi **đúng bằng** baseline (1.00 / 1.00 / 1.00 / 5.00).

**Corruption nào ảnh hưởng rõ nhất và vì sao?**

`drop_latest_records`. Khi đối chiếu `corruption_log.json` với `corrupted_answers.json`, `ground_truth_doc_ids` của cả 10 câu đều nằm trong 5 bài bị bỏ, nên không câu nào có thể hit. Vì mọi ground truth đã mất, lần chạy này **không đo được riêng** tác động của các lỗi khác lên metric. Dù vậy vẫn thấy dấu vết của chúng trong câu trả lời:
- `stale_date`: `eval_005` trả lời ngày `2021-06-02`, lấy từ một bài bị lùi 5 năm.
- `duplicate_rows`: 8/10 câu có một `paper_id` xuất hiện 2 lần trong top-4.
- `inject_text_noise`: `eval_002`, `eval_009` trả về câu chứa chuỗi rác.

**Kết quả nào khác với kỳ vọng ban đầu?**

- **Cùng một bộ lỗi, hit rate khác hẳn tùy thiết kế test set.** Trước khi merge PR #5, test set chọn bài rải đều từ mới đến cũ, và cùng 6 kịch bản lỗi (seed 42) cho hit rate corrupted 0.70: chỉ 3 câu về bài mới nhất bị miss. Sau merge, test set lấy 5 bài mới nhất và hit rate về 0.00. Kiểm tra bằng cách so `ground_truth_doc_ids` của hai phiên bản test set với danh sách `paper_ids` của bước `drop_latest_records`. Bài học cho vai trò tích hợp: thay đổi ở một module (test set) có thể làm đổi hẳn kết luận của cả pipeline, nên kết luận phải đi kèm phiên bản test set (SHA-256 `c3772946d68d`).
- **Trả lời đúng nhưng tìm sai.** `eval_003` (authors), `eval_007` và `eval_008` (category) có F1 = 1.00 dù hit = False: bài đứng đầu là bài khác có cùng tác giả hoặc chuyên ngành. Nếu chỉ nhìn metric câu trả lời, các câu này trông như không bị ảnh hưởng.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Data pipeline:** Giữ nguyên raw snapshot và làm sạch bằng một hàm thuần (cùng input thì cùng output) giúp repair trở thành "chạy lại" thay vì "vá". Đó là điều kiện để repair idempotent và chứng minh được bằng so sánh với baseline.
2. **Data quality/observability:** Quality gate và freshness bắt những lỗi khác nhau: GX bắt trùng lặp/rỗng, freshness bắt dữ liệu cũ. Cả hai đều cần, vì metric của agent không tách được lỗi nào gây ra thiệt hại, và có câu vẫn "đúng" dù tìm sai tài liệu.
3. **Ảnh hưởng của data đến RAG agent:** Dữ liệu bẩn không làm agent báo lỗi, mà làm nó trả lời sai một cách tự tin. Mất tài liệu gây hại cho retrieval, còn nhiễu văn bản gây hại cho câu trả lời. Chỉ đo đầu ra thì không biết nguyên nhân nằm ở tầng nào.

### Nếu có thêm thời gian

Làm cho judge accuracy so sánh được giữa các lần chạy:
- Cache verdict của judge theo `(question, answer)`: câu trả lời giống hệt thì dùng lại verdict cũ, không gọi LLM lại.
- Khi judge phải dùng heuristic, pipeline in cảnh báo rõ và cho phép chạy lại riêng bước judge.

Lý do: trong các lần chạy đầu (khi quota `gemini-3.5-flash` đã hết), số câu phải dùng heuristic là 7/10, 0/10, 4/10 ở 3 trạng thái, và judge accuracy repaired (0.90) lệch baseline (1.00) chỉ vì `eval_009` được chấm bằng hai cách khác nhau. Lần chạy cuối không gặp vấn đề này (0/10 ở cả 3 trạng thái) nhưng chỉ vì còn quota, không phải vì pipeline đảm bảo được. Cách đo: chạy `run_corruption_flow.py` hai lần liên tiếp. Nếu `judge_accuracy` của baseline và repaired bằng nhau khi dữ liệu trùng khớp, và `judge_fallback_count` bằng nhau giữa các trạng thái, thì cải thiện đã có tác dụng.

## 10. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Đức Thắng
**Ngày xác nhận:** 2026-09-25
