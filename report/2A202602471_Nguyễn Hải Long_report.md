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
| Benchmark test set | `src/evaluation/testset.py` — `build_test_set()`, `load_or_create_test_set()`, `TestSet`, `_pick_papers()`, `_pair_across_categories()` | Clean DataFrame | `data/eval/test_set.json` (10 câu, 5 dạng) | Hoàn thành |
| Metrics mở rộng | `src/evaluation/metrics.py` — `_summarize_by_question_type()`, `judge_fallback_count` trong `evaluate_pipeline()` | Kết quả từng câu | `*_metrics.json` có thêm chỉ số theo dạng câu hỏi và số câu chấm bằng heuristic | Hoàn thành |
| Báo cáo Pha 1 | `src/observability/reporting.py` — `generate_phase1_report()` | Source summary, metrics, quality, freshness | `data/reports/phase1_report.md` | Hoàn thành |
| Báo cáo đối chiếu 3 trạng thái | `reporting.py` — `generate_corruption_report()` | Metrics, quality, freshness của 3 trạng thái, corruption log, repair summary | `data/reports/corruption_report.md` | Hoàn thành |

Tôi nhận bảng clean từ Data Foundation để sinh câu hỏi, dùng index của RAG Specialist qua `answer_question`, và nhận kết quả quality/freshness từ Observability để đưa vào báo cáo. Pipeline Lead gọi các hàm của tôi trong `phase1.py` và `corruption_flow.py`.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                         | Thành viên/module được hỗ trợ | Kết quả                    |
| ------------------------------------ | ------------------------------------ | ---------------------------- |
| Đối chiếu hướng dẫn với rubric về số câu hỏi và tên trường | Cả nhóm | Chốt 10 câu (theo `RUBRIC.md`), mỗi mẫu có cả `type` lẫn `question_type` để cả lệnh kiểm tra của hướng dẫn và `metrics.py` đều chạy |
| Cung cấp `by_question_type` cho log của pipeline | Pipeline Lead — `corruption_flow.py` | Phát hiện được hit rate của riêng câu summary giảm 1.00 → 0.00 |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao       | Cách xác minh         |
| --------------------------- | ----------------------------- | ------------------------- | ----------------------- |
| Sinh 10 câu: 2 × {summary, authors, date, categories, multi_hop} | `build_test_set()` | `test_set.json`, mỗi mẫu có `id, type, question_type, question, ground_truth, ground_truth_doc_ids` | Lệnh CP2 → `Test set gồm 10 câu hỏi` / `Sinh được 10 câu hỏi test` |
| Chọn bài rải đều từ mới đến cũ | `_pick_papers()` | Câu hỏi phủ cả bài mới nhất và bài cũ | `eval_001` hỏi về bài mới nhất (2026-07-22) |
| Ghép cặp multi_hop khác `primary_category` | `_pair_across_categories()` | 2 câu liên ngành (vd. Software Engineering × Artificial Intelligence) | Đọc `test_set.json` |
| Giữ test set cố định giữa các lần chạy | `load_or_create_test_set()` | File không bị sinh lại khi chạy lại pipeline | `test_set.json` giữ nguyên thời điểm tạo qua các lần chạy `run_phase1.py` |
| Xuất 2 báo cáo Markdown | `generate_phase1_report()`, `generate_corruption_report()` | `phase1_report.md` (5 mục), `corruption_report.md` (6 mục) | Mở file sau khi chạy 2 pipeline |

Output cụ thể phần việc của tôi tạo ra:

Bảng đầu tiên của `data/reports/corruption_report.md`, có cột chênh lệch so với baseline:

| Metric | Baseline | Corrupted | Repaired | Corrupted vs Baseline | Repaired vs Baseline |
|---|---|---|---|---|---|
| Retrieval hit rate | 1.00 | 0.70 | 1.00 | -0.30 | +0.00 |
| Mean token F1 | 0.95 | 0.84 | 0.95 | -0.10 | +0.00 |

Ngay dưới bảng là dòng ghi số câu judge phải chấm bằng heuristic ở mỗi trạng thái (7/10, 0/10, 4/10), để người đọc biết judge accuracy có so sánh được hay không.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Muốn chứng minh dữ liệu bẩn làm RAG trả lời sai, cần một "đề thi" có đáp án cố định, đo được cả phần tìm kiếm lẫn phần trả lời. Kết quả của 3 trạng thái phải được trình bày sao cho người đọc thấy ngay mức sụt giảm, nguyên nhân, và mức độ tin cậy của từng chỉ số.

### Cách triển khai

- **Chọn bài (`_pick_papers`):**
  - Bỏ bài có dấu nháy đơn trong tiêu đề, vì `qa.py` tìm tiêu đề bằng regex `'([^']+)'`.
  - Sắp xếp mới → cũ, lấy 12 bài cách đều nhau (bước = số bài / 12). Nhờ vậy test set luôn có bài mới nhất, là nhóm bị ảnh hưởng khi mất dữ liệu tươi.
- **Sinh câu hỏi:** 8 bài đầu chia cho 4 dạng một-bài. Mẫu câu khớp với nhánh trích xuất của `qa.py`: `Who authored …` → `authors_joined`; `When was … published?` → `published`; `What categories …` → `categories_joined`; câu summary lấy câu đầu tiên của summary làm ground truth. 4 bài còn lại ghép thành 2 cặp multi_hop khác `primary_category`; ground truth là câu đầu của cả hai summary, `ground_truth_doc_ids` gồm 2 DOI.
- **Cố định test set:** `load_or_create_test_set` đọc file có sẵn nếu đủ 6 trường bắt buộc. Chỉ sinh lại khi `refresh=True` hoặc file sai schema.
- **Metrics:** thêm `by_question_type` (hit rate / token F1 / judge accuracy theo từng dạng) và `judge_fallback_count` (đếm câu có `reasoning` bắt đầu bằng `Fallback heuristic`).
- **Báo cáo:** hàm `_table` dùng chung, escape ký tự `|`. Phase 1 report có 5 mục: nguồn, GX, freshness, đánh giá, demo agent. Corruption report có 6 mục: chỉ số + chênh lệch, chỉ số theo dạng câu, 6 kịch bản lỗi, GX corrupted và repaired, freshness, repair và kết luận.

### Input, output và contract

| Thành phần                   | Mô tả                                     |
| ------------------------------ | ------------------------------------------- |
| Input                          | Clean DataFrame (`paper_id, title, summary, authors_joined, categories_joined, published, primary_category`); dict metrics / quality / freshness từ các module khác |
| Output                         | `test_set.json` (list mẫu 6 trường); metrics bổ sung `by_question_type{}`, `judge_fallback_count`; `phase1_report.md`; `corruption_report.md` |
| Module phụ thuộc             | `retrieval/qa.py` (mẫu câu hỏi phải khớp logic trích xuất), `core/utils.py` (`first_sentence`, `write_json`, `write_text`) |
| Module sử dụng output        | `evaluation/metrics.py` (`evaluate_pipeline` đọc `question_type`, `ground_truth_doc_ids`), `pipelines/phase1.py`, `pipelines/corruption_flow.py` |
| Điều kiện lỗi cần xử lý | Ít hơn 12 bài dùng được → `ValueError`; tiêu đề có dấu nháy đơn; file test set cũ thiếu trường; không có corruption log hoặc repair summary (report vẫn xuất, ghi chú thiếu); judge chấm bằng heuristic (ghi rõ trong report) |

### Cách xác minh

```bash
python -c "from core.config import load_settings; from evaluation.testset import load_or_create_test_set; import pandas as pd; s=load_settings(); df=pd.read_json(s.paths.clean_json); ts=load_or_create_test_set(df, s.paths.test_set_json); print(f'Tín hiệu hoàn thành: Test set gồm {len(ts.samples)} câu hỏi')"
python script/run_phase1.py
python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** Test set 10 câu; `baseline_metrics.json` có `retrieval_hit_rate` và `mean_token_f1`; `phase1_report.md` và `corruption_report.md` được sinh ra đầy đủ.
- **Kết quả thực tế:**
  - Lệnh đầu in `Tín hiệu hoàn thành: Test set gồm 10 câu hỏi`. Hướng dẫn Pha 3 ghi "5 câu", nhưng `RUBRIC.md`, `CHECKPOINTS.md`, `SUBMISSION.md` đều yêu cầu 10 câu; xem mục 5.
  - Baseline: hit rate 1.00, token F1 0.95. Hai report được sinh ra đầy đủ.
- **Artifact/log:** `data/eval/test_set.json`, `data/results/{baseline,corrupted,repaired}_{metrics,answers}.json`, `data/reports/phase1_report.md`, `data/reports/corruption_report.md`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Hướng dẫn Pha 3 yêu cầu 5 câu (1 câu × 5 dạng, có `multi_hop`), trường `type`, lệnh kiểm tra in "5 câu hỏi". Trong khi `RUBRIC.md` (tiêu chí chấm) yêu cầu 10 câu qua 4 dạng, và `metrics.py` đọc trường `question_type`.
- **Các phương án đã cân nhắc:**
  1. **5 câu** theo hướng dẫn, chỉ có trường `type`.
  2. **10 câu, 4 dạng** theo rubric, chỉ có `question_type`.
  3. **10 câu = 2 × 5 dạng** (gồm `multi_hop`), mỗi mẫu có cả `type` và `question_type`; số câu mỗi dạng chỉnh bằng hằng số `QUESTIONS_PER_TYPE`.
- **Phương án đã chọn:** (3).
- **Lý do:**
  - Rubric là tiêu chí chấm điểm nên ưu tiên số câu 10.
  - Giữ `multi_hop` theo hướng dẫn vì đây là dạng khó duy nhất, cho thấy giới hạn của QA trích xuất.
  - Hai trường cùng tồn tại giúp cả lệnh kiểm tra của hướng dẫn lẫn `metrics.py` đều chạy mà không sửa code cũ.
  - Về đo lường: với 5 câu, mỗi câu sai làm hit rate đổi 0.20, quá thô để phân biệt mức suy giảm. Với 10 câu, mỗi câu là 0.10.
  - Trade-off: lệnh kiểm tra của hướng dẫn in 10 thay vì 5. Nếu giảng viên yêu cầu đúng 5 câu, chỉ cần đặt `QUESTIONS_PER_TYPE = 1`.
- **Bằng chứng quyết định phù hợp:** với 10 câu, corrupted cho hit rate 0.70, và bảng theo dạng câu hỏi chỉ ra đúng chỗ hỏng: summary 1.00 → 0.00, authors 1.00 → 0.50, còn date/categories nguyên vẹn. Với 5 câu, mỗi dạng chỉ có 1 mẫu, không phân biệt được "hỏng một phần" (authors 0.50) với "hỏng hết".

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Dữ liệu repaired trùng khớp baseline (`matches_baseline=True`, token F1 cùng 0.95), nhưng `judge_accuracy` repaired = 0.90, baseline = 1.00. Khác biệt nằm ở `eval_009` (multi_hop): câu trả lời giống hệt ở hai trạng thái (F1 = 0.73), baseline chấm *đúng*, repaired chấm *sai* với lý do `The model answer only addresses the first paper and leaves out the contribution of the second paper regarding Agentic RAG.`
- **Lệnh hoặc bước tái hiện:** So `judge` của `eval_009` trong `baseline_answers.json` và `repaired_answers.json`; đếm câu có `reasoning` bắt đầu bằng `Fallback heuristic` ở mỗi trạng thái.
- **Nguyên nhân gốc:**
  - Hai trạng thái được chấm bằng hai cách khác nhau. `_judge_answer` gọi LLM; nếu lỗi thì dùng heuristic theo token F1 (F1 ≥ 0.5 → điểm 3 → đúng).
  - API key Gemini dùng gói miễn phí, giới hạn 20 request/ngày/model (`429 RESOURCE_EXHAUSTED … limit: 20`). Vì vậy số câu dùng heuristic thay đổi theo lần chạy: baseline 7/10, corrupted 0/10, repaired 4/10.
  - `eval_009` ở baseline được chấm bằng heuristic (0.73 ≥ 0.5 → đúng), ở repaired được Gemini chấm (nhận ra câu trả lời thiếu bài thứ hai → sai).
- **Cách xử lý:** Thêm `judge_fallback_count` vào metrics và một dòng cảnh báo ngay dưới bảng chỉ số trong cả hai report, để người đọc biết judge accuracy không so sánh được giữa các trạng thái. Hit rate và token F1 không cần LLM, nên được dùng làm chỉ số chính cho kết luận.

Chưa xử lý xong:

- **Phạm vi bị ảnh hưởng:** `judge_accuracy`, `mean_judge_score` trong 3 file `*_metrics.json` và 2 report.
- **Những gì đã loại trừ:**
  - Dữ liệu khác nhau: `matches_baseline=True`, F1 từng câu giống hệt.
  - Retrieval khác nhau: `eval_009` hit ở cả hai trạng thái.
  - LLM chấm không ổn định giữa hai lần gọi: không phải, vì ở baseline câu này không hề được LLM chấm.
- **Bước tiếp theo:** Chạy lại cả 3 trạng thái với cùng một cách chấm: (a) `LLM_PROVIDER=mock`, khi đó cả 3 đều dùng heuristic và `judge_fallback_count = 10/10` ở mọi trạng thái; hoặc (b) chạy khi còn quota để cả 3 đều là 0/10. Kiểm chứng: `judge_fallback_count` bằng nhau ở 3 file metrics, và `judge_accuracy` repaired = baseline.
- **Điều học được:** Một metric chỉ so sánh được khi *cách đo* giống nhau. Phải ghi lại cách mỗi con số được tạo ra (ở đây là LLM hay heuristic) ngay cạnh con số.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. **Crossref → vector index:** dữ liệu thô được giữ nguyên, parse và làm sạch thành bảng có `text_for_embedding`, qua quality gate, rồi được MiniLM embed vào Chroma. Test set của tôi được sinh từ chính bảng clean này, nên mỗi câu hỏi gắn với một `paper_id` thật đang có trong index baseline.
2. **Evaluation set và ground truth:**
   - `retrieval_hit`: ít nhất một DOI trong `ground_truth_doc_ids` nằm trong top-4 → đo retrieval.
   - `token_f1`: độ trùng token giữa câu trả lời và `ground_truth` → đo nội dung câu trả lời.
   - `judge`: chấm mức đúng về nghĩa.

   Tách ba lớp giúp khoanh vùng lỗi. Summary corrupted: hit 0.00 → lỗi ở retrieval (bài không còn). multi_hop `eval_010`: vẫn hit nhưng F1 0.40 → lỗi ở nội dung (summary bị chèn rác).
3. **Quality vs freshness:** quality check kiểm tra từng dòng có hợp lệ không (trùng, rỗng, quá ngắn) và chặn pipeline. Freshness kiểm tra cả tập có quá cũ không (tỉ lệ bài quá 180 ngày ≤ 25%) và chỉ cảnh báo. Trong báo cáo, tôi đặt hai tín hiệu ở hai mục riêng vì chúng bắt các lỗi khác nhau.
4. **Cùng test set:** nếu sinh lại câu hỏi từ bảng corrupted, `_pick_papers` sẽ chỉ chọn trong 22 bài còn lại, không có câu nào hỏi về 5 bài bị mất, và hit rate corrupted có thể vẫn là 1.00. Test set cố định là "thước đo" không đổi, nên metric thay đổi chỉ có thể do dữ liệu.
5. **Repair thành công:** `repaired_metrics.json` có hit rate 1.00 và token F1 0.95 bằng baseline; `repaired_quality_report.json` PASS; freshness FRESH; `matches_baseline=True`. Judge accuracy (0.90) không dùng làm tiêu chí vì lý do ở mục 6.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal          | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ---------------------- | -------: | --------: | -------: | ------------------------- |
| `retrieval_hit_rate` |     1.00 |      0.70 |     1.00 | Theo dạng câu: summary 1.00 → 0.00 → 1.00; authors 1.00 → 0.50 → 1.00; các dạng khác giữ 1.00 |
| `mean_token_f1`      |     0.95 |      0.84 |     0.95 | multi_hop thấp nhất ở cả baseline (0.73): QA chỉ trích từ tài liệu đứng đầu nên luôn thiếu bài thứ hai |
| `judge_accuracy`     |     1.00 |      0.70 |     0.90 | Chỉ corrupted được LLM chấm toàn bộ (0/10 heuristic); baseline 7/10, repaired 4/10 heuristic. Không so sánh trực tiếp được |
| `mean_judge_score`   |     4.60 |      3.90 |     4.60 | Cùng lưu ý |
| Quality checks         | PASS (0/6) | FAIL (2/6) | PASS (0/6) | |
| Freshness status       | FRESH (4.2%) | STALE (36.4%) | FRESH (4.2%) | |

### Kết luận từ số liệu

1. Tiêm 6 loại lỗi → gate FAIL (unique, độ dài summary) và freshness STALE → hit rate 1.00 → 0.70 (−0.30), token F1 0.95 → 0.84 (−0.10); summary là dạng câu hỏng nặng nhất (hit 0.00).
2. Dựng lại từ raw → gate PASS, FRESH → hit rate và token F1 về đúng baseline (+0.00 so với baseline ở cả hai chỉ số).

**Corruption nào ảnh hưởng rõ nhất và vì sao?**

`drop_latest_records`. Test set chọn bài cách đều từ mới nhất, nên `eval_001` (bài mới nhất), `eval_002` và `eval_003` đều hỏi về bài nằm trong 5 bài bị bỏ. Đây là 3/3 câu mất hit. Bảng theo dạng câu cho thấy thiệt hại dồn vào summary (0/2) và authors (1/2), vì đó là các dạng được gán cho những bài mới nhất.

**Kết quả nào khác với kỳ vọng ban đầu?**

- Tôi kỳ vọng judge accuracy repaired bằng baseline, vì dữ liệu trùng khớp. Thực tế 0.90 so với 1.00. Nguyên nhân là cách chấm khác nhau (mục 6), đã kiểm tra bằng cách so `judge.reasoning` của `eval_009` ở hai trạng thái.
- Multi_hop F1 = 0.73 ngay cả ở baseline: câu hỏi multi-hop phơi bày giới hạn của QA trích xuất một tài liệu. Đó là giới hạn của hệ thống QA, không phải của dữ liệu.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Data pipeline:** Test set cũng là một artifact cần quản lý như dữ liệu: phải cố định, có phiên bản, và chỉ sinh lại có chủ đích (`REFRESH_TEST_SET=1`).
2. **Data quality/observability:** Chỉ số tổng hợp che mất chi tiết. Hit rate 0.70 không cho biết summary hỏng hoàn toàn còn date nguyên vẹn; bảng theo dạng câu hỏi mới cho thấy điều đó.
3. **Ảnh hưởng của data đến RAG agent:** Mất tài liệu phá retrieval, còn bẩn nội dung phá câu trả lời. Cần cả hit rate lẫn token F1 để phân biệt hai kiểu hỏng.

### Nếu có thêm thời gian

Thêm chỉ số thứ hạng (MRR, mean reciprocal rank) bên cạnh hit@4. Lý do: hit@4 chỉ cho đúng/sai. Ví dụ dòng nhân đôi đẩy bài đúng từ hạng 1 xuống hạng 3 vẫn được tính là hit, nên `duplicate_rows` hoàn toàn vô hình với metric hiện tại. Cách đo: tính `1 / rank` của DOI đúng đầu tiên trong `retrieved_doc_ids`; nếu MRR corrupted thấp hơn baseline ở các câu có ground truth bị nhân đôi (`eval_005`, `eval_009`) trong khi hit rate không đổi, chỉ số mới đã bắt được thứ hit@4 bỏ sót.

## 10. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Hải Long
**Ngày xác nhận:** 2026-09-26
