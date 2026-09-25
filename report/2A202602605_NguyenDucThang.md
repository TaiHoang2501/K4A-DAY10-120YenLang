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
| Pipeline Pha 1 (baseline) | `src/pipelines/phase1.py` — `main()`, `_ensure_test_set()`, `_run_agent_demo()` | `Settings`, raw snapshot, module của các thành viên 2–5 | `papers_clean.csv/json`, collection `papers-baseline`, `test_set.json`, `baseline_metrics.json`, `phase1_report.md` | Hoàn thành |
| Pipeline corruption → repair → compare | `src/pipelines/corruption_flow.py` — `main()`, `_evaluate_state()`, `_check_quality()`, `_matches_baseline()` | Artifact baseline, `crossref_records.json` | `corrupted_*`, `repaired_*` (clean/embeddings/metrics/answers), collection `papers-corrupted` / `papers-repaired`, `corruption_report.md` | Hoàn thành |
| Cấu hình & contract đường dẫn | `src/core/config.py` — thêm `paths.test_set_json` | Hướng dẫn lab | Đường dẫn artifact thống nhất cho mọi module | Hoàn thành |
| Entry point | `script/run_phase1.py`, `script/run_corruption_flow.py` | — | Hai lệnh chạy end-to-end | Hoàn thành (dùng sẵn, gọi `main()`) |

Phần việc của tôi nằm ở giữa: nhận output của Data Foundation (thành viên 2: `build_clean_dataframe`, `load_raw_records`), đưa qua quality gate của Observability (thành viên 4), index bằng module của RAG Specialist (thành viên 3), rồi giao cho Evaluation & Reporting (thành viên 5) chấm điểm và xuất báo cáo.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                         | Thành viên/module được hỗ trợ | Kết quả                    |
| ------------------------------------ | ------------------------------------ | ---------------------------- |
| Debug pipeline treo ở bước evaluate | RAG Specialist — `retrieval/llm.py` | Thêm `timeout` (45 giây) + `max_retries` (1) cho mọi LLM client, chỉnh bằng env `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`; `run_phase1.py` chạy hết với EXIT=0 |
| Debug treo khi load embedding model | RAG Specialist — `retrieval/embeddings.py` | Load MiniLM từ cache local (`local_files_only=True`), chỉ lên mạng khi chưa có cache |
| Chốt contract giữa các module | Evaluation & Reporting — `evaluation/metrics.py`, `observability/reporting.py` | Thống nhất thêm `by_question_type`, `judge_fallback_count` vào metrics; `generate_corruption_report()` nhận thêm `corruption_log`, `repair_summary` |
| Rút gọn lỗi provider trong report | `phase1.py` — `_short_error()` | Lỗi 429 của Gemini (kèm JSON dài) chỉ giữ 160 ký tự đầu trong `agent_demo_answers.json` / report |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao       | Cách xác minh         |
| --------------------------- | ----------------------------- | ------------------------- | ----------------------- |
| Nối 7 bước Pha 1, quality gate FAIL thì dừng trước khi index | `src/pipelines/phase1.py` | 5 artifact bắt buộc của CP3 | `python script/run_phase1.py` → log `[phase1] 1/7 … 7/7`, EXIT=0 |
| Giữ test set cố định giữa các lần chạy, chỉ sinh lại khi `REFRESH_TEST_SET=1` hoặc ground truth không còn trong corpus | `phase1.py` — `_ensure_test_set()` | `data/eval/test_set.json` (10 câu) dùng chung cho 3 trạng thái | Chạy lại pipeline → file không đổi |
| Nối luồng corruption → evaluate → repair → compare | `src/pipelines/corruption_flow.py` | Bảng 3 trạng thái trên console + `corruption_report.md` | `python script/run_corruption_flow.py` → EXIT=0 |
| Kiểm tra repair có idempotent (trùng khớp baseline) | `corruption_flow.py` — `_matches_baseline()` | `identical to baseline=True` | Log `[corruption] Repaired: 24 rows rebuilt from raw, identical to baseline=True` |
| Tách 3 Chroma collection để so sánh độc lập | `corruption_flow.py` — `_evaluate_state()` gọi `LocalEmbeddingIndex.build(df, settings, embeddings_path)` | `papers-baseline`, `papers-corrupted`, `papers-repaired` | `data/embeddings/papers_embeddings*.json` ghi đúng `collection_name` |

Output cụ thể phần việc của tôi tạo ra:

Bảng đối chiếu trong `data/reports/corruption_report.md` và trên console khi chạy `run_corruption_flow.py`: retrieval hit rate 1.00 → 0.70 → 1.00, token F1 0.95 → 0.84 → 0.95. Quality gate corrupted FAIL (2/6 expectation), repaired PASS (0/6). Dữ liệu repaired trùng khớp baseline (`matches_baseline=True`).

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Mỗi thành viên viết một module riêng: lấy dữ liệu, làm sạch, quality gate, index, test set, chấm điểm, báo cáo. Nếu không có ai nối lại thì không có lệnh nào chạy được từ đầu đến cuối, và không có cách lặp lại thí nghiệm "dữ liệu bẩn làm RAG sai mà không báo lỗi". Vai trò của tôi là biến các module đó thành hai pipeline chạy được bằng một lệnh, có thứ tự đúng, có điểm dừng khi dữ liệu xấu, và cho kết quả lặp lại được.

### Cách triển khai

**Pha 1 (`phase1.py`)** chạy tuần tự:

1. `fetch_source_records` — mặc định đọc snapshot offline, đặt `REFRESH_SOURCE=1` thì gọi API.
2. `build_clean_dataframe` + `save_clean_dataframe`.
3. `run_data_quality_checks("baseline")` + `build_freshness_report`. Nếu gate FAIL thì `raise RuntimeError`, **không** index: dữ liệu bẩn không được vào vector store.
4. `LocalEmbeddingIndex.build` → collection `papers-baseline`.
5. `_ensure_test_set`: dùng lại test set đã có. Chỉ sinh lại khi có `REFRESH_TEST_SET=1` hoặc khi `ground_truth_doc_ids` trỏ tới bài không còn trong corpus.
6. `evaluate_pipeline` → `baseline_metrics.json`.
7. Demo agent (lỗi LLM được bắt và ghi lại, không làm dừng pipeline) → `generate_phase1_report`.

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
| Module phụ thuộc             | `ingestion.crossref`, `ingestion.cleaning`, `ingestion.corruption`, `observability.quality`, `observability.reporting`, `retrieval.index`, `retrieval.agent`, `evaluation.testset`, `evaluation.metrics` |
| Module sử dụng output        | `script/run_phase1.py`, `script/run_corruption_flow.py`; corruption flow dùng output của Pha 1 (`clean_json`, `baseline_metrics.json`, `test_set.json`) |
| Điều kiện lỗi cần xử lý | Quality gate baseline/repaired FAIL → dừng; thiếu artifact baseline → báo chạy Pha 1; test set trỏ tới bài không còn → sinh lại; LLM timeout/429 → judge dùng heuristic, agent demo ghi lỗi rút gọn; API Crossref lỗi → fallback snapshot |

### Cách xác minh

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** Cả hai lệnh chạy xong. Pha 1 sinh đủ 5 artifact của CP3. Corruption flow cho thấy chỉ số giảm ở trạng thái corrupted và phục hồi ở trạng thái repaired.
- **Kết quả thực tế:**
  - `run_phase1.py`: EXIT=0, log `3/7 Quality gate success=True (0/6 failed), is_fresh=True`, `4/7 Indexed 24 documents into Chroma collection 'papers-baseline'`, `6/7 Baseline hit_rate=1.00 token_f1=0.95 judge_accuracy=1.00 (heuristic fallback on 7/10)`.
  - `run_corruption_flow.py`: EXIT=0, gate corrupted FAIL (`expect_column_values_to_be_unique(paper_id)`, `expect_column_value_lengths_to_be_between(summary)`), `is_fresh=False (8/22 stale)`; repaired PASS, `identical to baseline=True`; bảng 3 trạng thái ở mục 8.
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
  - Hit rate về lại 1.00 và token F1 về lại 0.95, **đúng bằng** baseline.
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
   - Tách hai lớp đo giúp biết lỗi nằm ở retrieval hay ở nội dung tài liệu. Ví dụ: `eval_010` vẫn hit nhưng F1 tụt từ 0.73 xuống 0.40 vì summary bị chèn ký tự rác.
3. **Quality checks vs freshness:**
   - Quality checks (GX) kiểm tra *tính hợp lệ của từng dòng/cột*: số dòng, not-null, unique `paper_id`, độ dài summary. Kết quả là PASS/FAIL, và FAIL thì dừng pipeline.
   - Freshness kiểm tra *tuổi của cả tập dữ liệu*: tỉ lệ bài có `age_days > 180` phải ≤ 25%. Đây là tín hiệu cảnh báo (`is_fresh`), không làm dừng pipeline.
   - Lỗi `stale_date` qua được mọi expectation GX, và chỉ freshness bắt được (8/22 = 36.4% → STALE).
4. **Cùng test set cho 3 trạng thái:** để biến duy nhất thay đổi là dữ liệu. Nếu mỗi trạng thái sinh test set riêng từ chính dữ liệu của nó (vd. từ bảng corrupted, vốn đã mất 5 bài mới nhất), câu hỏi sẽ tự né phần dữ liệu bị mất và chỉ số sẽ không giảm. Cách đó che đi đúng lỗi cần đo. Vì vậy `_ensure_test_set` giữ file cố định và corruption flow luôn đọc `paths.eval_testset` do Pha 1 tạo.
5. **Repair thành công dựa trên:**
   - `repaired_quality_report.json` PASS 6/6.
   - `repaired_freshness_report.json` `is_fresh=true` (1/24).
   - `matches_baseline=True` (nội dung trùng khớp baseline).
   - `repaired_metrics.json` có hit rate 1.00 và token F1 0.95, bằng baseline.
   - Judge accuracy không dùng làm tiêu chí chính, vì cách chấm khác nhau giữa các lần chạy (xem mục 8).

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal          | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ---------------------- | -------: | --------: | -------: | ------------------------- |
| `retrieval_hit_rate` |     1.00 |      0.70 |     1.00 | Cả 3 lần miss (`eval_001`, `002`, `003`) đều do `drop_latest_records`: bài ground truth không còn trong index |
| `mean_token_f1`      |     0.95 |      0.84 |     0.95 | Giảm do summary sai bài (câu summary 1.00 → 0.65) và ký tự rác (`eval_010` multi_hop 0.73 → 0.40) |
| `judge_accuracy`     |     1.00 |      0.70 |     0.90 | Không so sánh công bằng được: số câu chấm bằng heuristic là 7/10, 0/10, 4/10. Repaired chỉ lệch baseline ở `eval_009`: câu trả lời giống hệt (F1 0.73), nhưng baseline chấm bằng heuristic (đúng) còn repaired do Gemini chấm (sai vì chỉ nói về 1 trong 2 bài) |
| `mean_judge_score`   |     4.60 |      3.90 |     4.60 | Cùng lưu ý như `judge_accuracy` |
| Quality checks         | PASS (0/6 fail) | FAIL (2/6 fail) | PASS (0/6 fail) | Corrupted: `paper_id` không unique (6 dòng), summary < 30 ký tự (4 dòng) |
| Freshness status       | FRESH (1/24 = 4.2%) | STALE (8/22 = 36.4%) | FRESH (1/24 = 4.2%) | `stale_date` lùi 7 bài về 5 năm trước, vượt ngưỡng 25% |

### Kết luận từ số liệu

1. Tiêm 6 loại lỗi (bỏ 5 bài mới nhất, xóa 3 summary, chèn rác vào 3 summary, cắt 3 tiêu đề, lùi ngày 7 bài, nhân đôi 3 dòng) → quality gate FAIL (unique `paper_id`, độ dài summary) và freshness STALE (36.4%) → hit rate 1.00 → 0.70, token F1 0.95 → 0.84. RAG vẫn trả lời trơn tru, không báo lỗi gì (silent failure).
2. Dựng lại từ `crossref_records.json` bằng cùng code làm sạch → gate PASS 6/6, freshness FRESH (4.2%), nội dung trùng khớp baseline → hit rate và token F1 phục hồi **đúng bằng** baseline (1.00 / 0.95).

**Corruption nào ảnh hưởng rõ nhất và vì sao?**

`drop_latest_records` ảnh hưởng rõ nhất. Khi đối chiếu `corruption_log.json` với `corrupted_answers.json`, cả 3 câu mất hit đều có ground truth nằm trong 5 bài bị bỏ. Không có tài liệu thì retrieval không thể đúng, bất kể embedding tốt đến đâu. Test set được chọn rải đều từ mới đến cũ, nên câu hỏi về bài mới nhất bị ảnh hưởng trực tiếp. Tác động nặng thứ hai là `inject_text_noise`: vẫn hit, nhưng câu trả lời chứa ký tự rác (F1 0.40, judge chấm 1/5).

**Kết quả nào khác với kỳ vọng ban đầu?**

- Tôi kỳ vọng `stale_date` và `duplicate_rows` cũng làm giảm chỉ số, nhưng thực tế các câu có ground truth bị lùi ngày (`eval_004`, `eval_007`) hoặc bị nhân đôi (`eval_005`) vẫn hit và F1 = 1.00.
  - Giả thuyết: retrieval chỉ dựa trên độ tương đồng ngữ nghĩa, không xét ngày. Dòng trùng chỉ chiếm thêm một chỗ trong top-k.
  - Đã kiểm tra bằng cách map từng `paper_id` trong log corruption sang kết quả từng câu.
  - Kết luận: hai loại lỗi này **không lộ ra ở metric của agent**, chỉ quality gate (unique) và freshness bắt được. Đây là lý do cần observability riêng, không thể chỉ dựa vào metric đầu ra.
- Judge accuracy của repaired (0.90) thấp hơn baseline (1.00) dù dữ liệu trùng khớp. Nguyên nhân là cách chấm khác nhau giữa các lần chạy do quota Gemini, không phải do dữ liệu (xem bảng trên).

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Data pipeline:** Giữ nguyên raw snapshot và làm sạch bằng một hàm thuần (cùng input thì cùng output) giúp repair trở thành "chạy lại" thay vì "vá". Đó là điều kiện để repair idempotent và chứng minh được bằng so sánh với baseline.
2. **Data quality/observability:** Quality gate và freshness bắt những lỗi khác nhau: GX bắt trùng lặp/rỗng, freshness bắt dữ liệu cũ. Cả hai đều cần, vì có lỗi (ngày bị lùi, dòng trùng) không làm giảm bất kỳ metric nào của agent.
3. **Ảnh hưởng của data đến RAG agent:** Dữ liệu bẩn không làm agent báo lỗi, mà làm nó trả lời sai một cách tự tin. Mất tài liệu gây hại cho retrieval, còn nhiễu văn bản gây hại cho câu trả lời. Chỉ đo đầu ra thì không biết nguyên nhân nằm ở tầng nào.

### Nếu có thêm thời gian

Làm cho judge accuracy so sánh được giữa các lần chạy:
- Cache verdict của judge theo `(question, answer)`: câu trả lời giống hệt thì dùng lại verdict cũ, không gọi LLM lại.
- Khi judge phải dùng heuristic, pipeline in cảnh báo rõ và cho phép chạy lại riêng bước judge.

Lý do: hiện judge accuracy của repaired lệch baseline chỉ vì `eval_009` được chấm bằng hai cách khác nhau, và quota free-tier 20 request/ngày khiến số câu phải dùng heuristic thay đổi giữa các lần chạy. Cách đo: chạy `run_corruption_flow.py` hai lần liên tiếp. Nếu `judge_accuracy` của baseline và repaired bằng nhau khi dữ liệu trùng khớp, và `judge_fallback_count` bằng nhau giữa các trạng thái, thì cải thiện đã có tác dụng.

## 10. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [ ] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [ ] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [ ] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [ ] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [ ] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [ ] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Đức Thắng
**Ngày xác nhận:** 2026-09-25
