# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Nguyễn Hải Long             |
| MSSV               | 2A202602471                     |
| Khóa/Lớp         | K4              |
| Tên nhóm         | 120YenLang     |
| Vai trò chính    | Evaluation & Reporting Lead (test set, metrics, báo cáo) |
| Repository         | https://github.com/TaiHoang2501/K4A-DAY10-120YenLang |
| Ngày hoàn thành | 2026-09-25               |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao  | Trạng thái                                 |
| ------------------ | --------------------- | ---------------- | ----------------- | -------------------------------------------- |
| Benchmark test set | `src/evaluation/testset.py` — `build_test_set()`, `load_or_create_test_set()`, `TestSet` | Clean DataFrame | `data/eval/test_set.json` (10 câu, 5 dạng) | Hoàn thành |
| Metrics mở rộng | `src/evaluation/metrics.py` — `_summarize_by_question_type()`, `judge_fallback_count` trong `evaluate_pipeline()` | Kết quả từng câu | `*_metrics.json` có thêm chỉ số theo dạng câu hỏi và số câu chấm bằng heuristic | Hoàn thành |
| Báo cáo Pha 1 | `src/observability/reporting.py` — `generate_phase1_report()` | Source summary, metrics, quality, freshness | `data/reports/phase1_report.md` | Hoàn thành |
| Báo cáo đối chiếu 3 trạng thái | `reporting.py` — `generate_corruption_report()` | Metrics của 3 trạng thái; quality và freshness của corrupted/repaired | `data/reports/corruption_report.md` | Hoàn thành |

Tôi nhận bảng clean từ Data Foundation để sinh câu hỏi, dùng index của RAG Specialist qua `answer_question`, và nhận kết quả quality/freshness từ Observability để đưa vào báo cáo. Pipeline Lead gọi các hàm của tôi trong `phase1.py` và `corruption_flow.py`.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                         | Thành viên/module được hỗ trợ | Kết quả                    |
| ------------------------------------ | ------------------------------------ | ---------------------------- |
| Đối chiếu hướng dẫn với rubric về số câu hỏi và tên trường | Cả nhóm | Chốt 10 câu (theo `RUBRIC.md`), mỗi mẫu có cả `type` lẫn `question_type` để cả lệnh kiểm tra của hướng dẫn và `metrics.py` đều chạy |
| Cung cấp `by_question_type` trong file metrics | Pipeline Lead, cả nhóm khi phân tích | Thấy được token F1 corrupted theo dạng: date 0.00, category 1.00, dù hit rate mọi dạng đều 0.00 |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao       | Cách xác minh         |
| --------------------------- | ----------------------------- | ------------------------- | ----------------------- |
| Sinh 10 câu: 2 × {summary, authors, date, category, multi_hop} | `build_test_set()` | `test_set.json`, mỗi mẫu có `id, type, question_type, question, ground_truth, ground_truth_doc_ids` | Lệnh CP2 → `Test set gồm 10 câu hỏi` / `Sinh được 10 câu hỏi test` |
| Chọn 5 bài đầu của bảng clean (`df.iloc[0..4]`, sắp xếp mới nhất trước) | `build_test_set()` | Mỗi bài được hỏi 2 lần theo các dạng khác nhau | `eval_001` hỏi về bài mới nhất (2026-07-22) |
| 2 câu multi_hop ghép 2 trong 5 bài | `build_test_set()` | `eval_009` (bài 2 + bài 5), `eval_010` (bài 4 + bài 1); `ground_truth_doc_ids` có 2 DOI | Đọc `test_set.json` |
| Giữ test set cố định giữa các lần chạy | `load_or_create_test_set()` | File không bị sinh lại khi chạy lại pipeline | `test_set.json` giữ nguyên thời điểm tạo qua các lần chạy `run_phase1.py` |
| Xuất 2 báo cáo Markdown | `generate_phase1_report()`, `generate_corruption_report()` | `phase1_report.md` (4 mục), `corruption_report.md` (3 mục) | Mở file sau khi chạy 2 pipeline |

Output cụ thể phần việc của tôi tạo ra:

Bảng đầu tiên của `data/reports/corruption_report.md` (lần chạy 2026-09-25 10:11Z), có cột chênh lệch:

| Metric | Baseline | Corrupted | Repaired | Impact / Delta |
| :--- | :--- | :--- | :--- | :--- |
| Retrieval Hit Rate | 100.00% | 0.00% | 100.00% | -100.00% -> +100.00% |
| Mean Token F1 | 1.0000 | 0.5133 | 1.0000 | -0.4867 -> +0.4867 |

Số câu judge phải chấm bằng heuristic nằm trong `judge_fallback_count` của từng file metrics (lần chạy cuối: 0/10 ở cả 3 trạng thái), để biết judge accuracy có so sánh được hay không.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Muốn chứng minh dữ liệu bẩn làm RAG trả lời sai, cần một "đề thi" có đáp án cố định, đo được cả phần tìm kiếm lẫn phần trả lời. Kết quả của 3 trạng thái phải được trình bày sao cho người đọc thấy ngay mức sụt giảm, nguyên nhân, và mức độ tin cậy của từng chỉ số.

### Cách triển khai

- **Chọn bài:** lấy 5 bài đầu của bảng clean (`p0`…`p4` = `df.iloc[0..4]`). Bảng clean đã sắp xếp mới nhất trước, nên đây là 5 bài mới nhất. Cần ít nhất 5 dòng, nếu không thì `ValueError`.
- **Sinh câu hỏi:** 10 câu cố định, mỗi dạng 2 câu. Mẫu câu khớp với nhánh trích xuất của `qa.py`:
  - summary (`p0`, `p1`): `What is the summary of the paper '<title>'?` → câu đầu tiên của summary.
  - authors (`p2`, `p3`): `Who authored the paper '<title>'?` → `authors_joined`.
  - date (`p4`, `p0`): `When was the paper '<title>' published?` → `published` dạng `YYYY-MM-DD`.
  - category (`p1`, `p4`): `What categories does the paper '<title>' belong to?` → `categories_joined`.
  - multi_hop (`p1` + `p4`, `p3` + `p0`): `What is the summary of the paper '<A>' in relation to '<B>'?` → câu đầu summary của bài A; `ground_truth_doc_ids` gồm cả 2 DOI.

  Mỗi mẫu có `id`, `type`, `question_type`, `question`, `ground_truth`, `ground_truth_doc_ids`.
- **Cố định test set:** `load_or_create_test_set(df, path, force_refresh=False)` đọc file có sẵn nếu là list không rỗng; chỉ sinh lại khi chưa có file hoặc `force_refresh=True` (`phase1.py` truyền `settings.refresh_test_set`, tức biến `REFRESH_TEST_SET`). `TestSet` kế thừa `list` và có thêm thuộc tính `.samples`.
- **Metrics:** thêm `by_question_type` (hit rate / token F1 / judge accuracy theo từng dạng) và `judge_fallback_count` (đếm câu có `reasoning` bắt đầu bằng `Fallback heuristic`).
- **Báo cáo:**
  - `phase1_report.md` có 4 mục: tổng quan nguồn; bảng chỉ số baseline kèm ngưỡng mục tiêu (hit rate ≥ 80%, token F1 ≥ 0.50, judge accuracy ≥ 70%, judge score ≥ 3.0) và PASS/WARN; trạng thái GX cùng từng expectation; freshness SLA.
  - `corruption_report.md` có 3 mục: bảng hit rate và token F1 của 3 trạng thái kèm cột chênh lệch; trạng thái gate corrupted/repaired; freshness SLA corrupted/repaired.

### Input, output và contract

| Thành phần                   | Mô tả                                     |
| ------------------------------ | ------------------------------------------- |
| Input                          | Clean DataFrame (`paper_id, title, summary, authors_joined, categories_joined, published, primary_category`); dict metrics / quality / freshness từ các module khác |
| Output                         | `test_set.json` (list mẫu 6 trường), trả về `TestSet`; metrics bổ sung `by_question_type{}`, `judge_fallback_count`; `phase1_report.md`; `corruption_report.md` |
| Module phụ thuộc             | `retrieval/qa.py` (mẫu câu hỏi phải khớp logic trích xuất), `core/utils.py` (`first_sentence`, `read_json`, `write_json`, `write_text`) |
| Module sử dụng output        | `evaluation/metrics.py` (`evaluate_pipeline` đọc `question_type`, `ground_truth_doc_ids`), `pipelines/phase1.py`, `pipelines/corruption_flow.py` |
| Điều kiện lỗi cần xử lý | Ít hơn 5 bài → `ValueError`; file test set hỏng hoặc rỗng → sinh lại; thiếu key trong metrics/quality/freshness → report dùng giá trị mặc định (`get(..., 0.0)`, `N/A`). **Chưa xử lý:** tiêu đề có dấu nháy đơn sẽ làm hỏng regex `'([^']+)'` của `qa.py` |

### Cách xác minh

```bash
python -c "from core.config import load_settings; from evaluation.testset import load_or_create_test_set; import pandas as pd; s=load_settings(); df=pd.read_json(s.paths.clean_json); ts=load_or_create_test_set(df, s.paths.test_set_json); print(f'Tín hiệu hoàn thành: Test set gồm {len(ts.samples)} câu hỏi')"
python script/run_phase1.py
python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** Test set 10 câu; `baseline_metrics.json` có `retrieval_hit_rate` và `mean_token_f1`; `phase1_report.md` và `corruption_report.md` được sinh ra đầy đủ.
- **Kết quả thực tế:**
  - Lệnh đầu in `Tín hiệu hoàn thành: Test set gồm 10 câu hỏi`. Hướng dẫn Pha 3 ghi "5 câu", nhưng `RUBRIC.md`, `CHECKPOINTS.md`, `SUBMISSION.md` đều yêu cầu 10 câu; xem mục 5.
  - Baseline: hit rate 1.00, token F1 1.00, judge accuracy 1.00. Hai report được sinh ra đầy đủ.
- **Artifact/log:** `data/eval/test_set.json`, `data/results/{baseline,corrupted,repaired}_{metrics,answers}.json`, `data/reports/phase1_report.md`, `data/reports/corruption_report.md`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Hướng dẫn Pha 3 yêu cầu 5 câu (1 câu × 5 dạng, có `multi_hop`), trường `type`, lệnh kiểm tra in "5 câu hỏi". Trong khi `RUBRIC.md` (tiêu chí chấm) yêu cầu 10 câu qua 4 dạng, và `metrics.py` đọc trường `question_type`.
- **Các phương án đã cân nhắc:**
  1. **5 câu** theo hướng dẫn, chỉ có trường `type`.
  2. **10 câu, 4 dạng** theo rubric, chỉ có `question_type`.
  3. **10 câu = 2 × 5 dạng** (gồm `multi_hop`), mỗi mẫu có cả `type` và `question_type`.
- **Phương án đã chọn:** (3).
- **Lý do:**
  - Rubric là tiêu chí chấm điểm nên ưu tiên số câu 10.
  - Giữ `multi_hop` theo hướng dẫn vì đây là dạng khó duy nhất, cho thấy giới hạn của QA trích xuất.
  - Hai trường cùng tồn tại giúp cả lệnh kiểm tra của hướng dẫn lẫn `metrics.py` đều chạy mà không sửa code cũ.
  - Về đo lường: với 5 câu, mỗi câu sai làm hit rate đổi 0.20, quá thô để phân biệt mức suy giảm. Với 10 câu, mỗi câu là 0.10.
  - Trade-off: lệnh kiểm tra của hướng dẫn in 10 thay vì 5. Danh sách câu hỏi đang viết cố định trong `build_test_set`, nên muốn đổi số câu phải sửa danh sách, và 10 câu dùng chung 5 bài (hệ quả ở mục 8).
- **Bằng chứng quyết định phù hợp:** ở lần chạy cuối, hit rate corrupted là 0.00 ở mọi dạng, nhưng token F1 theo dạng vẫn phân biệt rõ mức hỏng: date 0.00, multi_hop 0.36, authors 0.50, summary 0.70, category 1.00. Với 2 câu mỗi dạng thấy được "hỏng một phần" (authors 0.50: 1 câu tình cờ đúng, 1 câu sai); với 1 câu mỗi dạng chỉ còn đúng/sai.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn (lần chạy đầu ngày 2026-09-25, trước khi merge PR #5):** Dữ liệu repaired trùng khớp baseline (`matches_baseline=True`, token F1 cùng 0.95), nhưng `judge_accuracy` repaired = 0.90, baseline = 1.00. Khác biệt nằm ở `eval_009` (multi_hop): câu trả lời giống hệt ở hai trạng thái (F1 = 0.73), baseline chấm *đúng*, repaired chấm *sai* với lý do `The model answer only addresses the first paper and leaves out the contribution of the second paper regarding Agentic RAG.`
- **Lệnh hoặc bước tái hiện:** So `judge` của `eval_009` trong `baseline_answers.json` và `repaired_answers.json`; đếm câu có `reasoning` bắt đầu bằng `Fallback heuristic` ở mỗi trạng thái.
- **Nguyên nhân gốc:**
  - Hai trạng thái được chấm bằng hai cách khác nhau. `_judge_answer` gọi LLM; nếu lỗi thì dùng heuristic theo token F1 (F1 ≥ 0.5 → điểm 3 → đúng).
  - API key Gemini dùng gói miễn phí, giới hạn 20 request/ngày/model (`429 RESOURCE_EXHAUSTED … limit: 20`). Vì vậy số câu dùng heuristic thay đổi theo lần chạy: baseline 7/10, corrupted 0/10, repaired 4/10.
  - `eval_009` ở baseline được chấm bằng heuristic (0.73 ≥ 0.5 → đúng), ở repaired được Gemini chấm (nhận ra câu trả lời thiếu bài thứ hai → sai).
- **Cách xử lý:** Thêm `judge_fallback_count` vào `*_metrics.json`, để biết judge accuracy có so sánh được giữa các trạng thái không. (Phiên bản `reporting.py` trước merge còn in dòng cảnh báo này ngay dưới bảng chỉ số; bản hiện tại không in, nên phải đọc trong file metrics.) Hit rate và token F1 không cần LLM, nên được dùng làm chỉ số chính cho kết luận.

Chưa xử lý xong:

- **Phạm vi bị ảnh hưởng:** `judge_accuracy`, `mean_judge_score` trong 3 file `*_metrics.json` và 2 report.
- **Những gì đã loại trừ:**
  - Dữ liệu khác nhau: `matches_baseline=True`, F1 từng câu giống hệt.
  - Retrieval khác nhau: `eval_009` hit ở cả hai trạng thái.
  - LLM chấm không ổn định giữa hai lần gọi: không phải, vì ở baseline câu này không hề được LLM chấm.
- **Bước tiếp theo:** Chạy lại cả 3 trạng thái với cùng một cách chấm: (a) `LLM_PROVIDER=mock`, khi đó cả 3 đều dùng heuristic và `judge_fallback_count = 10/10` ở mọi trạng thái; hoặc (b) chạy khi còn quota để cả 3 đều là 0/10. Kiểm chứng: `judge_fallback_count` bằng nhau ở 3 file metrics, và `judge_accuracy` repaired = baseline.
- **Kết quả kiểm chứng (lần chạy 2026-09-25 10:10–10:11Z, `gemini-3.5-flash-lite` còn quota, cách (b)):** `judge_fallback_count` = 0/10 ở cả 3 trạng thái, và `judge_accuracy` repaired = baseline = 1.00. Khi cách chấm giống nhau, chênh lệch biến mất. Tuy vậy đây mới là kiểm chứng nhờ còn quota; pipeline vẫn chưa tự đảm bảo điều này.
- **Điều học được:** Một metric chỉ so sánh được khi *cách đo* giống nhau. Phải ghi lại cách mỗi con số được tạo ra (ở đây là LLM hay heuristic) ngay cạnh con số.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. **Crossref → vector index:** dữ liệu thô được giữ nguyên, parse và làm sạch thành bảng có `text_for_embedding`, qua quality gate, rồi được MiniLM embed vào Chroma. Test set của tôi được sinh từ chính bảng clean này, nên mỗi câu hỏi gắn với một `paper_id` thật đang có trong index baseline.
2. **Evaluation set và ground truth:**
   - `retrieval_hit`: ít nhất một DOI trong `ground_truth_doc_ids` nằm trong top-4 → đo retrieval.
   - `token_f1`: độ trùng token giữa câu trả lời và `ground_truth` → đo nội dung câu trả lời.
   - `judge`: chấm mức đúng về nghĩa.

   Tách ba lớp giúp thấy lỗi mà một lớp bỏ sót. Category corrupted: hit 0.00 nhưng F1 1.00 và judge chấm đúng → câu trả lời "đúng" nhưng lấy từ bài khác có cùng chuyên ngành; chỉ retrieval hit cho thấy lỗi. Date corrupted: hit 0.00 và F1 0.00 (`eval_005` trả `2021-06-02` từ một bài bị lùi ngày).
3. **Quality vs freshness:** quality check kiểm tra từng dòng có hợp lệ không (trùng, rỗng, quá ngắn) và chặn pipeline. Freshness kiểm tra cả tập có quá cũ không (tỉ lệ bài quá 180 ngày ≤ 25%) và chỉ cảnh báo. Trong báo cáo, tôi đặt hai tín hiệu ở hai mục riêng vì chúng bắt các lỗi khác nhau.
4. **Cùng test set:** nếu sinh lại câu hỏi từ bảng corrupted, `build_test_set` sẽ chỉ chọn trong 22 bài còn lại, không có câu nào hỏi về 5 bài bị mất, và hit rate corrupted có thể vẫn là 1.00. Test set cố định là "thước đo" không đổi, nên metric thay đổi chỉ có thể do dữ liệu.
5. **Repair thành công:** `repaired_metrics.json` có hit rate 1.00, token F1 1.00, judge accuracy 1.00 bằng baseline (lần chạy cuối cả 3 trạng thái đều do LLM chấm nên so sánh được); `repaired_quality_report.json` PASS; freshness FRESH; `matches_baseline=True`.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal          | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ---------------------- | -------: | --------: | -------: | ------------------------- |
| `retrieval_hit_rate` |     1.00 |      0.00 |     1.00 | 0.00 ở cả 5 dạng: test set sinh từ 5 bài mới nhất, đúng 5 bài bị bỏ |
| `mean_token_f1`      |     1.00 |      0.51 |     1.00 | Theo dạng: date 0.00, multi_hop 0.36, authors 0.50, summary 0.70, category 1.00 |
| `judge_accuracy`     |     1.00 |      0.60 |     1.00 | Cả 3 trạng thái do Gemini chấm (0/10 heuristic) nên so sánh được; nhưng judge chấm đúng 5/5 hai câu chứa chuỗi rác (`eval_002`, `eval_009`) |
| `mean_judge_score`   |     5.00 |      3.40 |     5.00 | Cùng lưu ý |
| Quality checks         | PASS (0/6) | FAIL (2/6) | PASS (0/6) | |
| Freshness status       | FRESH (4.2%) | STALE (36.4%) | FRESH (4.2%) | |

Số liệu từ lần chạy 2026-09-25 10:10–10:11Z trên code đã merge của `main`; test set SHA-256 `c3772946d68d`.

### Kết luận từ số liệu

1. Tiêm 6 loại lỗi → gate FAIL (unique, độ dài summary) và freshness STALE → hit rate 1.00 → 0.00 (−1.00), token F1 1.00 → 0.51 (−0.49), judge accuracy 1.00 → 0.60; date là dạng câu hỏng nặng nhất (F1 0.00).
2. Dựng lại từ raw → gate PASS, FRESH → cả 4 chỉ số về đúng baseline (1.00 / 1.00 / 1.00 / 5.00).

**Corruption nào ảnh hưởng rõ nhất và vì sao?**

`drop_latest_records`. `build_test_set` hiện tại sinh 10 câu từ 5 bài đầu của bảng clean (`df.iloc[0..4]`, sắp xếp mới nhất trước), và đó chính là 5 bài bị bỏ. Đối chiếu `ground_truth_doc_ids` với `corruption_log.json`: 10/10 câu mất ground truth. Thiết kế test set quyết định lỗi nào "thấy được": trước khi merge PR #5, test set chọn bài rải đều và cùng bộ lỗi chỉ làm miss 3/10 câu (hit rate 0.70).

**Kết quả nào khác với kỳ vọng ban đầu?**

- Tôi kỳ vọng judge accuracy corrupted gần với hit rate, vì câu trả lời lấy từ bài sai. Thực tế 0.60 so với 0.00. Kiểm tra từng câu trong `corrupted_answers.json`: 6 câu được chấm đúng dù hit = False. Có 4 câu đúng "tình cờ" (bài khác có cùng tác giả hoặc chuyên ngành, hoặc summary gần giống), và 2 câu (`eval_002`, `eval_009`) chứa chuỗi rác `[1*[~70z6<6` mà judge vẫn chấm 5/5. LLM judge dễ dãi với chuỗi rác, nên không thể dùng một mình.
- Multi_hop ở baseline đạt F1 = 1.00 (lần chạy trước merge là 0.73). Đọc `test_set.json` thì thấy `ground_truth` của câu multi_hop chỉ là câu đầu summary của bài thứ nhất, dù `ground_truth_doc_ids` có 2 DOI. Như vậy multi_hop hiện chưa thực sự kiểm tra khả năng tổng hợp hai tài liệu.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Data pipeline:** Test set cũng là một artifact cần quản lý như dữ liệu: phải cố định, có phiên bản, và chỉ sinh lại có chủ đích (`REFRESH_TEST_SET=1`).
2. **Data quality/observability:** Chỉ số tổng hợp che mất chi tiết. Token F1 0.51 không cho biết câu date sai hoàn toàn (0.00) còn câu category trông như nguyên vẹn (1.00); bảng theo dạng câu hỏi mới cho thấy điều đó.
3. **Ảnh hưởng của data đến RAG agent:** Mất tài liệu phá retrieval, còn bẩn nội dung phá câu trả lời. Cần cả hit rate lẫn token F1 để phân biệt hai kiểu hỏng.

### Nếu có thêm thời gian

Sửa `build_test_set` để chọn bài rải đều từ mới đến cũ thay vì 5 bài mới nhất (`df.iloc[0..4]`). Lý do: ở lần chạy cuối, cả 10 ground truth nằm trong 5 bài bị `drop_latest_records` bỏ, nên hit rate corrupted bị ép về 0.00 và không đo được riêng tác động của `inject_text_noise`, `truncate_title`, `duplicate_rows`. Cách đo: sau khi sửa, đối chiếu `ground_truth_doc_ids` với `corruption_log.json`: phải có câu hỏi về bài thuộc từng nhóm lỗi, và hit rate corrupted theo dạng câu hỏi không còn đồng loạt 0.00.

## 10. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [ ] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [ ] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [ ] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [ ] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [ ] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [ ] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Hải Long
**Ngày xác nhận:** [YYYY-MM-DD]
