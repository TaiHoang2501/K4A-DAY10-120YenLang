# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Ngô Tiến Dũng             |
| MSSV               | 2A202602374                |
| Khóa/Lớp         | Khóa 4 (K4)                |
| Tên nhóm         | 120YENLANG                 |
| Vai trò chính    | Observability Lead (quality gate GX 1.x, Freshness SLA, tiêm lỗi)  |
| Repository         | https://github.com/TaiHoang2501/K4A-DAY10-120YenLang. |
| Ngày hoàn thành | 2026-09-25                 |

---

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao  | Trạng thái                                 |
| ------------------ | --------------------- | ---------------- | ----------------- | -------------------------------------------- |
| Quality gate GX 1.x | `src/observability/quality.py` — `run_data_quality_checks()` | Clean DataFrame, `Settings`, `report_name` | `{report_name, success, evaluated_expectations, successful_expectations, unsuccessful_expectations, expectations[]}` + `data/quality/<report_name>_quality_report.json` | Hoàn thành (còn 2 lỗ hổng, xem mục 6) |
| Freshness SLA | `quality.py` — `build_freshness_report()` | DataFrame có `age_days`, `published` | `freshness_report.json` (`stale_rows`, `stale_ratio`, `is_fresh`, `sla_status`, `warning` khi stale) | Hoàn thành |
| 6 kịch bản tiêm lỗi | `src/ingestion/corruption.py` — `corrupt_clean_dataframe()`, `_inject_noise()` | Clean DataFrame, đường dẫn log, `seed=42` | DataFrame bẩn + `data/results/corruption_log.json` | Hoàn thành |

Gate của tôi đứng giữa Data Foundation (bảng clean) và RAG Specialist (index). `phase1.py` hiện in trạng thái gate ra console (`Quality Check Status: True`) nhưng chưa dừng khi FAIL; `corruption_flow.py` dừng (`raise`) nếu bảng repaired không PASS. Bộ tiêm lỗi tạo đầu vào cho phần đánh giá corrupted của Evaluation.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                         | Thành viên/module được hỗ trợ | Kết quả                    |
| ------------------------------------ | ------------------------------------ | ---------------------------- |
| Chốt quy ước tên file report `<report_name>_quality_report.json` | Pipeline Lead — `config.py` | `run_data_quality_checks(df, s, "baseline")` ghi đúng vào `paths.baseline_quality_report`, tương tự cho `corrupted`/`repaired` |
| Giải thích lỗi `SyntaxError: unterminated string literal` khi chạy lệnh kiểm tra CP1 trên PowerShell | Cả nhóm (máy Windows) | Nguyên nhân: PowerShell không coi `\"` là ký tự escape nên cắt đôi câu lệnh. Cách chạy đúng: gán `ok=res['success']` rồi in `{ok}`, hoặc chạy trong Git Bash |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao       | Cách xác minh         |
| --------------------------- | ----------------------------- | ------------------------- | ----------------------- |
| Context GX 1.x ephemeral + 4 loại expectation (6 expectation) | `run_data_quality_checks()` | Baseline PASS 6/6 | Lệnh CP1 → `Quality check status = True` |
| Freshness SLA: cảnh báo khi > 25% bài có `age_days > 180` | `build_freshness_report()` | Baseline 1/24 = 4.2% → FRESH | `data/quality/freshness_report.json` |
| 6 kịch bản lỗi, seed cố định, mỗi kịch bản 2–5 tác động lên dòng riêng | `corrupt_clean_dataframe()` | 24 → 22 dòng; log ghi `paper_id` từng dòng bị tác động | Lệnh CP4 → `Corrupted 22 dòng`; `corruption_log.json` có 6 bước |
| Chứng minh gate bắt được dữ liệu bẩn | `corrupted_quality_report.json` | FAIL: unique `paper_id` (6 dòng), độ dài summary (4 dòng); STALE 36.4% | Log `run_corruption_flow.py` |

Output cụ thể phần việc của tôi tạo ra:

`data/quality/corrupted_quality_report.json`: `success=false`, `unsuccessful_expectations=2` (unique `paper_id` 6 dòng, độ dài summary 4 dòng). `data/quality/corrupted_freshness_report.json`: `stale_rows=8`, `total_rows=22`, `is_fresh=false`, `sla_status="WARNING (Stale)"`, kèm cảnh báo `⚠️ CẢNH BÁO: 36.4% bài báo cũ hơn 180 ngày (vượt ngưỡng 25%). Cần cập nhật dữ liệu mới!`. Cùng dữ liệu đó, agent vẫn trả lời bình thường, không báo lỗi. Gate là nơi duy nhất phát hiện vấn đề.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Dữ liệu bẩn không làm RAG báo lỗi, chỉ làm nó trả lời sai (silent failure). Cần một "chốt kiểm soát" tự động kiểm tra dữ liệu *trước* khi vào vector store, và một bộ tiêm lỗi có kiểm soát để chứng minh chốt đó bắt được lỗi thật.

### Cách triển khai

- **GX 1.x:** `gx.get_context(mode="ephemeral")` (chạy trên RAM, không sinh file) → `data_sources.add_pandas` → `add_dataframe_asset` → `add_batch_definition_whole_dataframe`. Tạo một `ExpectationSuite`, thêm:
  - `ExpectTableRowCountToBeBetween(5, 5000)`
  - `ExpectColumnValuesToNotBeNull` cho `paper_id`, `title`, `text_for_embedding`
  - `ExpectColumnValuesToBeUnique(paper_id)`
  - `ExpectColumnValueLengthsToBeBetween(summary, min_value=30)`

  Sau đó đăng ký `gx.ValidationDefinition(data=batch_def, suite=suite)` và chạy `.run(batch_parameters={"dataframe": df})`. Mỗi kết quả được rút gọn thành `expectation_type / kwargs / success / result{observed_value, element_count, unexpected_count, unexpected_percent}`.
- **Không chuẩn hóa trước khi validate:** DataFrame được đưa thẳng vào GX. Vì vậy chuỗi rỗng không bị coi là null (hệ quả ở mục 6).
- **Freshness:** hàm riêng `build_freshness_report()`: `stale_ratio = số dòng age_days > 180 / tổng số dòng`, `is_fresh = stale_ratio ≤ 0.25`, `sla_status` là `PASSED (Fresh)` hoặc `WARNING (Stale)`, và thêm key `warning` khi stale. Freshness **không** tính vào `success` của quality gate: dữ liệu cũ vẫn hợp lệ, đây là tín hiệu SLA cần làm mới nguồn.
- **Tiêm lỗi:** `random.Random(42)`.
  1. Bỏ 20% bài mới nhất.
  2. Xáo trộn các dòng còn lại và lấy các tập rời nhau: xóa summary (3), chèn rác (3), cắt tiêu đề còn 7 ký tự (3), lùi ngày 5 năm (35%, tức 7 dòng) và cộng tương ứng vào `age_days`.
  3. Nhân đôi 3 dòng.
  4. Tạo lại `summary_chars` và `text_for_embedding` bằng hàm của cleaning.
  5. Ghi log từng bước kèm `paper_id` và giá trị gốc/giá trị mới.

  Tỉ lệ 35% cho `stale_date` được chọn để vẫn vượt ngưỡng 25% sau khi thêm dòng nhân đôi.

### Input, output và contract

| Thành phần                   | Mô tả                                     |
| ------------------------------ | ------------------------------------------- |
| Input                          | DataFrame theo `CLEAN_COLUMNS` (cần ít nhất `paper_id`, `title`, `summary`, `text_for_embedding`, `published`, `age_days`); `Settings.freshness_threshold_days=180` |
| Output                         | Quality: `{report_name, success, evaluated_expectations, successful_expectations, unsuccessful_expectations, expectations[]}`. Freshness: `{latest_published, oldest_published, stale_rows, total_rows, stale_ratio, threshold_days, max_stale_ratio, is_fresh, sla_status, total_documents, stale_documents, fresh_documents, stale_threshold_days, warning?}`. Corruption log: `{generated_at, seed, input_rows, output_rows, scenarios, steps[]}` |
| Module phụ thuộc             | `great_expectations` 1.18.0, `ingestion/cleaning.py` (`CLEAN_COLUMNS`, `build_text_for_embedding`), `core/utils.py` |
| Module sử dụng output        | `pipelines/phase1.py` (in trạng thái gate và SLA), `pipelines/corruption_flow.py` (dừng nếu repaired FAIL), `observability/reporting.py` (trạng thái GX + freshness trong 2 report) |
| Điều kiện lỗi cần xử lý | Dataframe rỗng → freshness trả `sla_status="PASSED (Empty)"`. **Chưa xử lý:** title là chuỗi rỗng và summary là `None` đều lọt qua gate (mục 6) |

### Cách xác minh

```bash
python -c "from core.config import load_settings; from observability.quality import run_data_quality_checks; import pandas as pd; s=load_settings(); df=pd.read_json(s.paths.clean_json); res=run_data_quality_checks(df, s, 'test'); ok=res['success']; print(f'Tín hiệu hoàn thành: Quality check status = {ok}')"
python -c "from core.config import load_settings; from ingestion.corruption import corrupt_clean_dataframe; import pandas as pd; s=load_settings(); df=pd.read_json(s.paths.clean_json); c=corrupt_clean_dataframe(df, s.paths.corruption_log); print(f'Tín hiệu hoàn thành: Corrupted {len(c)} dòng')"
```

- **Kết quả mong đợi:** Gate `True` trên dữ liệu sạch; bộ tiêm lỗi ghi log 6 kịch bản; gate `False` trên dữ liệu bẩn.
- **Kết quả thực tế:** `Quality check status = True`; `Corrupted 22 dòng`; `corruption_log.json` có 6 bước (5 / 3 / 3 / 3 / 7 / 3 dòng); corrupted gate FAIL (unique 6, độ dài summary 4), freshness 8/22 → STALE.
- **Artifact/log:** `data/quality/baseline_quality_report.json`, `corrupted_quality_report.json`, `repaired_quality_report.json`, `freshness_report.json`, `data/results/corruption_log.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Freshness vượt ngưỡng có nên làm `success=False` (chặn pipeline) giống các expectation GX không?
- **Các phương án đã cân nhắc:**
  1. **Gộp freshness vào gate:** dữ liệu cũ → `success=False` → dừng index.
  2. **Tách riêng:** `success` chỉ phản ánh GX; freshness là hàm riêng, trả `is_fresh`, `sla_status` và `warning`.
- **Phương án đã chọn:** (2).
- **Lý do:**
  - Hai tín hiệu đo hai thứ khác nhau. GX đo *tính hợp lệ* (trùng/rỗng là dữ liệu sai, không được phục vụ). Freshness đo *độ mới*: bài cũ vẫn đúng, chỉ là cần cập nhật nguồn.
  - Chặn pipeline vì dữ liệu cũ sẽ làm hệ thống ngừng phục vụ hoàn toàn, trong khi phục vụ dữ liệu cũ kèm cảnh báo thường tốt hơn không phục vụ gì.
  - Tách riêng cũng cho báo cáo biết *loại* sự cố.
  - Trade-off: nếu không ai đọc cảnh báo, dữ liệu cũ vẫn được phục vụ. Vì vậy cảnh báo được ghi log, `sla_status` được in ra console (`Freshness SLA Status: PASSED (Fresh)`) và đưa vào cả hai report.
- **Bằng chứng quyết định phù hợp:**
  - Ở trạng thái corrupted, hai tín hiệu bắt hai nhóm lỗi khác nhau. GX FAIL vì trùng/rỗng. Freshness STALE vì `stale_date`, lỗi mà **không** expectation GX nào bắt được (6/6 expectation vẫn không liên quan đến ngày).
  - Baseline có 1/24 bài quá 180 ngày (4.2%): vẫn FRESH và gate vẫn PASS, đúng như mong muốn.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Khi thử gate với dữ liệu cố tình làm bẩn (thêm 2 dòng trùng, xóa trắng 1 summary, đặt `age_days=400` cho 10 dòng), phiên bản đầu của `quality.py` (trước khi merge PR #5) trả `success= False [('expect_column_values_to_be_unique', 'paper_id')]`. Chỉ lỗi trùng bị bắt; **summary rỗng lọt qua** expectation độ dài ≥ 30 ký tự.
- **Lệnh hoặc bước tái hiện:** `bad = pd.concat([df, df.head(2)]); bad.loc[3, 'summary'] = ''; run_data_quality_checks(bad, s, 'negative_test')`.
- **Nguyên nhân gốc:**
  - Phiên bản đầu có bước chuẩn hóa đổi chuỗi rỗng thành `None` cho mọi cột kiểm tra, **kể cả `summary`**, để not-null bắt được giá trị trắng.
  - Nhưng `ExpectColumnValueLengthsToBeBetween` của GX **bỏ qua giá trị null** khi tính độ dài, nên summary rỗng biến mất khỏi phép kiểm tra. Chính bước chuẩn hóa để bắt lỗi đã che lỗi.
- **Cách xử lý:** Phiên bản đầu được sửa để `summary` rỗng hoặc null đều thành chuỗi độ dài 0. Sau khi merge PR #5, `quality.py` hiện tại không còn bước chuẩn hóa, và tôi chạy lại negative test trên code hiện tại (2026-09-25):

  | Phép thử | Kết quả gate hiện tại |
  |---|---|
  | `summary = ""` | FAIL: `expect_column_value_lengths_to_be_between(summary)`, 1 dòng, **bắt đúng** |
  | `summary = None` | PASS: **không bắt được**, GX bỏ qua null khi đo độ dài |
  | `title = ""` | PASS: **không bắt được**, not-null không coi chuỗi rỗng là null |

  Kịch bản `blank_summary` của bộ tiêm lỗi ghi chuỗi rỗng `""`, nên trong corruption flow gate vẫn bắt được (4 dòng).

Chưa xử lý xong:

- **Phạm vi bị ảnh hưởng:** `run_data_quality_checks()`: summary bị mất dưới dạng `None` và title rỗng sẽ lọt vào index mà gate vẫn PASS.
- **Những gì đã loại trừ:** Chuỗi rỗng ở summary (đã bắt đúng); dữ liệu sạch (vẫn PASS 6/6).
- **Bước tiếp theo:** Thêm `ExpectColumnValuesToNotBeNull(summary)`, và trước khi validate đổi chuỗi toàn khoảng trắng ở `title` thành `None` (không làm với `summary`, để giữ bài học của phiên bản đầu). Kiểm chứng: chạy lại 3 phép thử trên; cả 3 phải FAIL, và dữ liệu sạch vẫn PASS.
- **Điều học được:** Phải kiểm thử quality gate bằng dữ liệu *cố tình sai* (negative test), và chạy lại mỗi khi code gate thay đổi: sau merge, một lỗ hổng đã sửa ở phiên bản trước quay lại dưới dạng khác. Cần đọc kỹ cách mỗi expectation xử lý null và chuỗi rỗng.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. **Crossref → vector index:** payload thô (giữ nguyên) → `PaperRecord` → bảng clean (`age_days`, `text_for_embedding`) → **quality gate của tôi** → MiniLM embed → Chroma. Gate là cửa kiểm soát cuối cùng trước khi dữ liệu vào lớp phục vụ; hiện `phase1.py` mới chỉ in trạng thái gate, chưa dừng khi FAIL.
2. **Evaluation set:** ground-truth doc IDs cho phép tính retrieval hit (bài đúng có trong top-4 không), còn `ground_truth` cho phép tính token F1 và judge. Nhờ đó chứng minh được lỗi mà gate bắt (ví dụ bài mới nhất bị bỏ) thực sự làm agent trả lời sai: hit rate 1.00 → 0.00.
3. **Quality vs freshness:** quality (GX) là kiểm tra đúng/sai trên từng dòng/cột và chặn pipeline. Freshness là SLA trên toàn tập (tỉ lệ bài quá 180 ngày ≤ 25%), chỉ cảnh báo. Trong lab, `stale_date` chỉ freshness bắt được; `duplicate_rows` và `blank_summary` chỉ GX bắt được.
4. **Cùng test set:** để thay đổi của metric chỉ đến từ dữ liệu. Log corruption ghi `paper_id` của từng dòng bị tác động, nên đối chiếu được từng câu trong test set bị lỗi nào làm hỏng. Điều này chỉ làm được khi test set cố định.
5. **Repair thành công:** `repaired_quality_report.json` `success=true` (0/6 fail), `repaired_freshness_report.json` `is_fresh=true` (1/24), cộng với hit rate và token F1 của `repaired_metrics.json` bằng baseline (1.00 / 1.00).

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal          | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ---------------------- | -------: | --------: | -------: | ------------------------- |
| `retrieval_hit_rate` |     1.00 |      0.00 |     1.00 | Giảm do bỏ 5 bài mới nhất (mọi câu hỏi nhắm vào 5 bài này): lỗi mà freshness cũng phản ánh (`latest_published` lùi từ 2026-07-22 về 2026-06-12) |
| `mean_token_f1`      |     1.00 |      0.51 |     1.00 | Câu trả lời lấy từ bài khác, có bài bị chèn rác hoặc lùi ngày |
| `judge_accuracy`     |     1.00 |      0.60 |     1.00 | Cả 3 trạng thái do Gemini chấm (0/10 heuristic), nhưng judge chấm đúng 5/5 cả câu chứa chuỗi rác, nên không dùng làm bằng chứng chính |
| `mean_judge_score`   |     5.00 |      3.40 |     5.00 | Như trên |
| Quality checks         | PASS (0/6) | FAIL (2/6: unique 6 dòng, độ dài summary 4 dòng) | PASS (0/6) | Gate phân biệt rõ dữ liệu sạch và bẩn |
| Freshness status       | FRESH (1/24 = 4.2%) | STALE (8/22 = 36.4%) | FRESH (1/24 = 4.2%) | `oldest_published` corrupted = 2021-03-28 (lùi 5 năm) |

Số liệu từ lần chạy 2026-09-25 10:10–10:11Z trên code đã merge của `main`.

### Kết luận từ số liệu

1. Nhân đôi 3 dòng, xóa 3 summary, lùi ngày 7 dòng, bỏ 5 bài mới nhất → GX FAIL (unique, độ dài summary) và freshness STALE (36.4% > 25%) → hit rate 1.00 → 0.00, token F1 1.00 → 0.51.
2. Dựng lại từ raw snapshot → GX PASS 0/6 fail, freshness FRESH 4.2% → hit rate và token F1 về đúng 1.00 / 1.00.

**Corruption nào ảnh hưởng rõ nhất và vì sao?**

Với agent, `drop_latest_records` gây toàn bộ 10/10 câu miss, vì test set sinh từ đúng 5 bài mới nhất. Với observability, đó cũng là lỗi *khó bắt nhất* bằng GX: 22 dòng vẫn nằm trong khoảng 5–5000, không null, không trùng. Tín hiệu duy nhất là freshness (`latest_published` lùi gần 6 tuần) và số dòng giảm 24 → 22. Lỗi gây thiệt hại lớn nhất cho agent lại là lỗi gate bắt kém nhất. Vì vậy tôi đề xuất ngưỡng số dòng tương đối so với lần chạy trước (mục 9) thay vì khoảng tuyệt đối 5–5000.

**Kết quả nào khác với kỳ vọng ban đầu?**

- Tôi kỳ vọng `stale_date` chỉ làm freshness chuyển STALE, không ảnh hưởng câu trả lời. Thực tế `eval_005` (hỏi ngày xuất bản) trả lời `2021-06-02`: bài đứng đầu top-4 là một bài bị lùi 5 năm (vừa bị `stale_date` vừa bị `duplicate_rows`). Agent trả một ngày sai lệch 5 năm mà không cảnh báo gì; chỉ freshness report cho thấy dữ liệu có vấn đề. Đã kiểm tra bằng cách map `retrieved_doc_ids[0]` của từng câu với `paper_ids` trong `corruption_log.json`.
- `inject_text_noise` không có expectation nào bắt, nhưng 4/10 câu corrupted lấy bài bị chèn rác làm tài liệu đứng đầu, và LLM judge vẫn chấm đúng 5/5 hai câu chứa chuỗi rác (`eval_002`, `eval_009`). Đây là khoảng trống của gate hiện tại: cần thêm một expectation cho văn bản (vd. tỉ lệ ký tự không phải chữ cái trong `summary`).

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Data pipeline:** Gate phải đặt *trước* bước tạo index và có quyền dừng pipeline; một gate chỉ ghi log mà không chặn thì không bảo vệ được lớp phục vụ. `phase1.py` hiện tại đang ở đúng trạng thái đó: in `Quality Check Status` nhưng vẫn index dù FAIL.
2. **Data quality/observability:** Quality và freshness bổ sung cho nhau: mỗi bên bắt được lỗi mà bên kia bỏ sót. Gate phải được kiểm bằng dữ liệu cố tình sai.
3. **Ảnh hưởng của data đến RAG agent:** Agent không báo lỗi khi dữ liệu bẩn, chỉ trả lời sai một cách tự tin (`eval_005` trả ngày lệch 5 năm, `eval_002` trả về chuỗi có ký tự rác). Observability là nơi phát hiện những gì agent không tự báo.

### Nếu có thêm thời gian

Thêm expectation *so với lần chạy trước*: số dòng không giảm quá 5% và `max(published)` không lùi so với baseline. Lý do: `drop_latest_records` hiện chỉ lộ qua freshness, còn gate vẫn PASS phần số dòng (22 nằm trong khoảng 5–5000). Ngưỡng 5% chọn theo dữ liệu lab: 24 × 0.95 = 22.8 > 22 nên corrupted FAIL; ngưỡng 10% (21.6) thì không bắt được. Cách đo: chạy lại corruption flow; expectation mới phải FAIL ở corrupted và PASS ở baseline/repaired.

## 10. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Ngô Tiến Dũng  
**Ngày xác nhận:** 2026-09-25
