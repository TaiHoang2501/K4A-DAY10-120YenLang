# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Khóa/Lớp         | K4              |
| Tên nhóm         | 120YenLang     |
| Repository         | https://github.com/TaiHoang2501/K4A-DAY10-120YenLang |
| Ngày hoàn thành | 2026-09-25               |

### Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò chính | Module/deliverable sở hữu |
| --: | --- | --- | --- | --- |
| 1 | Nguyễn Đức Thắng | 2A202602605 | Pipeline Lead | `src/core/config.py`, `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py`, `script/`; tích hợp & debug end-to-end — [báo cáo](2A202602605_NguyenDucThang.md) |
| 2 | Trần Anh Quân | 2A202602598 | Data Foundation Owner | `src/ingestion/crossref.py`, `src/ingestion/cleaning.py` (`repair_clean_dataset`), `data/raw/` — [báo cáo](2A202602598_TranAnhQuan.md) |
| 3 | Hoàng Anh Tài | 2A202602612 | RAG Specialist | `src/retrieval/index.py`, `embeddings.py`, `qa.py`, `agent.py`, `llm.py`; 3 collection ChromaDB — [báo cáo](2A202602612_HoangAnhTai.md) |
| 4 | Ngô Tiến Dũng | 2A202602374 | Observability Lead | `src/observability/quality.py` (GX 1.x + Freshness SLA), `src/ingestion/corruption.py` — [báo cáo](2A202602374_NgoTienDung.md) |
| 5 | Nguyễn Hải Long | 2A202602471 | Evaluation & Reporting Lead | `src/evaluation/testset.py`, `src/evaluation/metrics.py`, `src/observability/reporting.py` — [báo cáo](2A202602471_NguyenHaiLong.md) |

## 2. Tóm tắt kết quả

**Tóm tắt của nhóm:**

Nhóm hoàn thành đủ hai pipeline. `python script/run_phase1.py` lấy 24 bài báo Crossref (chế độ snapshot offline), làm sạch, cho qua quality gate Great Expectations 1.x (PASS 6/6), index vào ChromaDB bằng `all-MiniLM-L6-v2` và đánh giá trên test set 10 câu. Baseline đạt retrieval hit rate 1.00, token F1 1.00, judge accuracy 1.00. Pipeline sinh đủ các artifact trong `data/raw`, `data/clean`, `data/embeddings`, `data/eval`, `data/results`, `data/quality` và `data/reports/phase1_report.md`.

`python script/run_corruption_flow.py` tiêm 6 loại lỗi (seed 42). Quality gate FAIL (trùng `paper_id` 6 dòng, summary < 30 ký tự 4 dòng) và freshness chuyển STALE (36.4% bài quá 180 ngày). Agent vẫn trả lời bình thường nhưng hit rate rơi về 0.00, token F1 về 0.51. Lỗi ảnh hưởng rõ nhất là **bỏ 5 bài mới nhất**, vì toàn bộ 10 câu hỏi được sinh từ đúng 5 bài đó.

Repair dựng lại dữ liệu từ raw snapshot bằng cùng code làm sạch. Kết quả trùng khớp baseline (`identical to baseline=True`), gate PASS, FRESH, và cả 4 chỉ số phục hồi 100% (hit rate 1.00, token F1 1.00, judge accuracy 1.00, judge score 5.00).

Giới hạn lớn nhất: test set tập trung vào 5 bài mới nhất, nên kết quả corrupted bị một loại lỗi chi phối và che tác động riêng của các lỗi khác. Ngoài ra, judge LLM phụ thuộc quota Gemini free-tier.

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

```text
Crossref REST API ──(REFRESH_SOURCE=1, lỗi 429/503/mạng → fallback)──┐
data/raw/crossref_response.json (snapshot, mặc định) ─────────────────┴─> parse_crossref_payload
    -> data/raw/crossref_records.json                                   (raw records, nguồn cho repair)
    -> build_clean_dataframe: normalize, age_days, dedupe, text_for_embedding
    -> data/clean/papers_clean.{csv,json}
    -> quality gate GX 1.x (6 expectations) + freshness SLA  -> data/quality/   (Pha 1 in trạng thái, chưa dừng khi FAIL)
    -> MiniLM embedding + Chroma collection "papers-baseline" -> data/chroma/, data/embeddings/
    -> test_set.json (10 câu, cố định) -> evaluate (hit rate, token F1, LLM judge) -> data/results/baseline_*
    -> phase1_report.md
─── run_corruption_flow.py ───
    papers_clean.json -> corrupt_clean_dataframe (6 kịch bản, seed 42) -> corruption_log.json
    -> quality gate (FAIL, vẫn index để đo thiệt hại) -> "papers-corrupted" -> evaluate cùng test set
    -> repair: crossref_records.json -> build_clean_dataframe -> gate PASS -> "papers-repaired" -> evaluate
    -> corruption_report.md + bảng 3 trạng thái trên console
```

### Trách nhiệm của từng khối

| Khối             | Input          | Xử lý chính             | Output/artifact          | Owner          |
| ----------------- | -------------- | -------------------------- | ------------------------ | -------------- |
| Ingestion         | Crossref API hoặc snapshot `crossref_response.json` | Dual-mode offline/online, timeout 30 giây, tối đa 3 lần thử khi lỗi mạng/lỗi khác, 429/503 → fallback snapshot ngay; parse DOI, bóc thẻ JATS, ngày ISO | `data/raw/crossref_records.json` | Trần Anh Quân |
| Cleaning          | `list[PaperRecord]` | Chuẩn hóa khoảng trắng, `age_days`, khử trùng lặp `paper_id`, loại dòng thiếu cả title lẫn summary, ghép `text_for_embedding` | `data/clean/papers_clean.{csv,json}` | Trần Anh Quân |
| Embedding/index   | Clean DataFrame | `all-MiniLM-L6-v2` (vector chuẩn hóa), Chroma cosine, xóa và tạo lại collection mỗi lần build | `data/chroma/`, `data/embeddings/papers_embeddings*.json` | Hoàng Anh Tài |
| Evaluation        | Clean DataFrame, index | Test set 10 câu × 5 dạng; hit@4, token F1, LLM judge (fallback heuristic) | `data/eval/test_set.json`, `data/results/*_metrics.json`, `*_answers.json` | Nguyễn Hải Long |
| Observability     | Clean DataFrame | GX 1.x ephemeral, 6 expectation; freshness: tỉ lệ `age_days > 180` ≤ 25% | `data/quality/*_quality_report.json`, `*freshness_report.json` | Ngô Tiến Dũng |
| Corruption/repair | Clean DataFrame; raw records | 6 kịch bản lỗi có log; repair = dựng lại từ raw | `data/results/corruption_log.json`, `data/clean/papers_clean_{corrupted,repaired}.*` | Ngô Tiến Dũng (corruption), Trần Anh Quân (repair) |
| Orchestration     | `Settings` (`.env`) | Thứ tự chạy 2 pipeline; Pha 1 in trạng thái gate, corruption flow cảnh báo khi corrupted FAIL và dừng nếu repaired FAIL; so sánh 3 trạng thái | `data/reports/phase1_report.md`, `corruption_report.md` | Nguyễn Đức Thắng |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình             | Giá trị sử dụng |
| ---------------------------- | ------------------- |
| `LLM_PROVIDER`             | `gemini`         |
| `LLM_MODEL`                | `gemini-3.5-flash-lite`         |
| Embedding model              | `sentence-transformers/all-MiniLM-L6-v2`         |
| Số lượng Crossref records | 24 (`max_results=24`, snapshot offline)         |
| Retrieval`top_k`           | 4         |
| Freshness threshold          | 180 ngày; cảnh báo khi > 25% bài vượt ngưỡng         |
| Random seed, nếu có        | 42 (`corrupt_clean_dataframe`)         |

Ngoài ra `LLM_TIMEOUT_SECONDS` (mặc định 45) và `LLM_MAX_RETRIES` (mặc định 1) giới hạn thời gian chờ mỗi request LLM. `REFRESH_SOURCE`, `REFRESH_TEST_SET`, `RUN_RAGAS` không được đặt.

### Lệnh cài đặt

```bash
uv sync
```

### Lệnh chạy

Với môi trường `.venv` đã kích hoạt:

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
```

> Trên PowerShell, các lệnh `python -c "..."` trong tài liệu có `\"` sẽ lỗi `SyntaxError: unterminated string literal`. Hãy chạy bằng Git Bash hoặc bỏ `\"` trong câu lệnh.

### Kết quả tái hiện

| Lệnh             | Trạng thái                                    | Thời điểm chạy gần nhất | Bằng chứng                         |
| ----------------- | ----------------------------------------------- | ----------------------------- | ------------------------------------ |
| Baseline pipeline | Thành công (EXIT=0) | 2026-09-25 10:10:43Z → 10:11:05Z (~22 giây) | Log `[1/7] … [7/7]`, `Quality Check Status: True`, `Retrieval Hit Rate: 100.00%`; `data/results/baseline_metrics.json`, `data/reports/phase1_report.md` |
| Corruption flow   | Thành công (EXIT=0) | 2026-09-25 10:11:05Z → 10:11:37Z (~32 giây) | Log `corrupted: quality gate success=False`, `Repaired: 24 rows rebuilt from raw, identical to baseline=True`; `data/reports/corruption_report.md` |

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính                | Giá trị                             |
| --------------------------- | ------------------------------------- |
| Source                      | Crossref REST API `https://api.crossref.org/works`. Lần chạy nộp bài dùng snapshot offline `data/raw/crossref_response.json` |
| Query/filter                | `query=agentic retrieval augmented generation large language model`, `filter=from-pub-date:<ngày chạy − 180 ngày>,has-abstract:true`, `rows=24` |
| Thời điểm lấy dữ liệu | Snapshot có sẵn trong repo; bài xuất bản từ 2026-03-28 đến 2026-07-22; pipeline chạy lúc 2026-09-25 10:10Z |
| Số record nhận được    | 24 item → 24 `PaperRecord` hợp lệ |
| Cơ chế retry/backoff      | Chỉ khi `REFRESH_SOURCE=1`: timeout 30 giây, tối đa 3 lần thử với lỗi mạng hoặc HTTP khác 200; gặp 429/503 thì chuyển sang snapshot ngay |

### Raw và clean schema

| Trường        | Kiểu dữ liệu | Bắt buộc?  | Ý nghĩa   | Xử lý khi thiếu/sai |
| --------------- | --------------- | ------------ | ----------- | ---------------------- |
| `paper_id` | str | Có | DOI (strip + lowercase), document ID dùng xuyên suốt index và ground truth | Thiếu DOI → bỏ item khi parse; trùng → giữ bản đầu tiên |
| `title` | str | Có (hoặc `summary`) | Tiêu đề đã gọn khoảng trắng | Thiếu cả title lẫn summary → bỏ record |
| `summary` | str | Có (hoặc `title`) | Abstract đã bóc thẻ JATS/HTML | Như trên; quality gate yêu cầu ≥ 30 ký tự |
| `authors` / `authors_joined` | list[str] / str | Không | Tác giả `given family`, và bản nối bằng `, ` | Tác giả rỗng bị lọc |
| `categories` / `categories_joined` / `primary_category` | list[str] / str / str | Không | `subject` của Crossref | Rỗng → chuỗi rỗng |
| `published` | str `YYYY-MM-DD` | Có | Ngày xuất bản từ `date-parts` | Không parse được → `age_days = None` |
| `updated` | str | Không | Ngày cập nhật | Fallback `created` → `published` |
| `age_days` | int | Có | `(run_date − published).days` | `None` nếu thiếu ngày |
| `summary_chars` | int | Không | Độ dài summary | — |
| `text_for_embedding` | str | Có | Văn bản 5 dòng đưa vào embedding | Quality gate kiểm tra not-null |
| `abs_url`, `pdf_url`, `comment` | str | Không | Link DOI và ghi chú nguồn | `https://doi.org/<doi>` |

### Quy tắc cleaning

| Quy tắc                                 | Quality dimension liên quan | Số record bị tác động | Cách xác minh      |
| ---------------------------------------- | ---------------------------- | -------------------------: | -------------------- |
| Bóc thẻ JATS/HTML (`<jats:p>…</jats:p>`) khỏi abstract | Validity | 24 | 24/24 abstract trong `crossref_response.json` chứa `<jats:`; `papers_clean.json` không còn thẻ |
| Bỏ item thiếu DOI hoặc thiếu cả title lẫn abstract | Completeness | 0 | Log parse `24/24 records hợp lệ` |
| Khử trùng lặp theo `paper_id` | Uniqueness | 0 | 24 dòng vào → 24 dòng ra; GX unique PASS |
| Loại dòng thiếu cả title lẫn summary | Completeness | 0 | 24 → 24 |
| Tính `age_days` từ `published` | Timeliness | 24 | `age_days` từ 65 đến 181 |

Cách tạo `text_for_embedding`, document ID và `age_days`:

- **Document ID** là DOI đã chuẩn hóa (`paper_id`). ID này dùng làm khóa khử trùng lặp, làm tiền tố `record_id` trong Chroma (`<paper_id>::<vị trí dòng>`, để dòng trùng trong bảng corrupted vẫn có id riêng) và làm `ground_truth_doc_ids` trong test set.
- **`age_days`** = số ngày từ `published` đến ngày chạy (UTC).
- **`text_for_embedding`** ghép 5 dòng `Title / Authors / Published / Categories / Summary`, để embedding mang được cả tiêu đề, tác giả, ngày và chuyên ngành, không chỉ nội dung tóm tắt. `corruption.py` dùng cùng hàm `build_text_for_embedding` để tạo lại văn bản sau khi tiêm lỗi.

## 6. Evaluation setup

| Thành phần                             | Cấu hình thực tế          |
| ---------------------------------------- | ----------------------------- |
| Số câu hỏi                            | 10                 |
| Các`question_type`                    | `summary`, `authors`, `date`, `category`, `multi_hop` (mỗi dạng 2 câu)                  |
| Ground-truth document ID                 | DOI của bài được hỏi; sinh từ 5 bài đầu của bảng clean (sắp xếp mới nhất trước). Câu `multi_hop` có 2 DOI, nhưng `ground_truth` chỉ là câu đầu summary của bài thứ nhất |
| Embedding model                          | `sentence-transformers/all-MiniLM-L6-v2`                  |
| Vector store/collection                  | ChromaDB persistent `data/chroma`, cosine; `papers-baseline` / `papers-corrupted` / `papers-repaired` (24 / 22 / 24 tài liệu) |
| Retrieval`top_k`                       | 4                   |
| LLM provider/model                       | `gemini` / `gemini-3.5-flash-lite` (judge); lần chạy này 0/10 câu phải dùng heuristic ở cả 3 trạng thái |
| Test set dùng chung cho ba trạng thái | `data/eval/test_set.json`, SHA-256 bắt đầu `c3772946d68d` |

Vì sao test set được giữ nguyên:

Muốn quy thay đổi của metric cho dữ liệu thì mọi thứ khác phải cố định, kể cả "đề thi". `load_or_create_test_set` chỉ sinh test set khi chưa có file (hoặc khi `REFRESH_TEST_SET=1`), và `corruption_flow.py` luôn đánh giá corrupted/repaired bằng đúng file mà Pha 1 dùng. Nếu sinh lại câu hỏi từ bảng corrupted, 5 bài bị mất sẽ không còn được hỏi, và hit rate corrupted sẽ không phản ánh thiệt hại.

## 7. Kết quả baseline

### Artifact checklist

| Artifact                 | Đường dẫn thực tế                | Trạng thái | Ghi chú   |
| ------------------------ | -------------------------------------- | ------------ | ---------- |
| Raw response/records     | `data/raw/crossref_response.json`, `crossref_records.json` | Có | 24 item / 24 record |
| Cleaned dataset          | `data/clean/papers_clean.csv`, `.json` | Có | 24 dòng, 16 cột |
| Embedding manifest/index | `data/embeddings/papers_embeddings.json`, `data/chroma/` | Có | Collection `papers-baseline`, 24 tài liệu |
| Evaluation set           | `data/eval/test_set.json` | Có | 10 câu, 5 dạng |
| Baseline metrics         | `data/results/baseline_metrics.json` | Có | Kèm `baseline_answers.json`, `agent_demo_answers.json` |
| Quality/freshness        | `data/quality/baseline_quality_report.json`, `freshness_report.json` | Có | PASS 6/6; FRESH |
| Baseline report          | `data/reports/phase1_report.md` | Có | |

### Baseline metrics

| Metric                 |       Giá trị | Diễn giải                             |
| ---------------------- | --------------: | --------------------------------------- |
| `retrieval_hit_rate` |     1.00 | 10/10 câu có bài đúng trong top-4 |
| `mean_token_f1`      |     1.00 | Câu trả lời trích xuất trùng hoàn toàn ground truth ở cả 5 dạng, kể cả `multi_hop` |
| `judge_accuracy`     |     1.00 | Gemini chấm 10/10 đúng, không câu nào phải dùng heuristic |
| `mean_judge_score`   |     5.00 | Điểm tối đa ở mọi câu |
| Ragas, nếu có        | N/A | Không chạy (`RUN_RAGAS` không bật) vì tốn thêm nhiều lời gọi LLM trong giới hạn quota free-tier |

Baseline đạt điểm tuyệt đối vì câu hỏi dạng trích xuất có tiêu đề chính xác trong câu hỏi, còn `qa.py` tra cứu đúng tiêu đề rồi lấy trường tương ứng từ metadata. Baseline này là mốc so sánh, không phải thước đo năng lực tổng quát của RAG.

## 8. Data quality và freshness

### Quality checks

| Check        | Quality dimension | Ngưỡng/kỳ vọng | Kết quả baseline      | Bằng chứng |
| ------------ | ----------------- | ------------------ | ----------------------- | ------------ |
| `ExpectTableRowCountToBeBetween` | Completeness (volume) | 5 – 5000 dòng | PASS (24) | `baseline_quality_report.json` |
| `ExpectColumnValuesToNotBeNull(paper_id)` | Completeness | 0 null | PASS (0/24) | như trên |
| `ExpectColumnValuesToNotBeNull(title)` | Completeness | 0 null | PASS (0/24) | như trên |
| `ExpectColumnValuesToNotBeNull(text_for_embedding)` | Completeness | 0 null | PASS (0/24) | như trên |
| `ExpectColumnValuesToBeUnique(paper_id)` | Uniqueness | 0 trùng | PASS (0/24) | như trên |
| `ExpectColumnValueLengthsToBeBetween(summary)` | Validity | ≥ 30 ký tự | PASS (0/24 vi phạm) | như trên |

### Freshness

| Thuộc tính               | Giá trị                           |
| -------------------------- | ----------------------------------- |
| Freshness được đo tại | Clean dataset (cột `age_days`, `published`) trước khi index |
| Timestamp mới nhất       | `published` = 2026-07-22 (cũ nhất 2026-03-28) |
| Ngưỡng freshness         | `age_days > 180` là stale; FRESH khi tỉ lệ stale ≤ 25% |
| Trạng thái baseline      | Fresh (`PASSED (Fresh)`) |
| Lý do                     | 1/24 bài (4.2%) quá 180 ngày: bài 2026-03-28 có `age_days = 181` |

## 9. Corruption scenarios và repair

| Corruption         | Cách tạo | Record bị tác động | Quality signal kỳ vọng | Tác động thực tế | Cách repair   |
| ------------------ | ---------- | ---------------------: | ------------------------ | --------------------- | -------------- |
| `drop_latest_records` | Bỏ 20% bài mới nhất theo `published` | 5 | Freshness: `latest_published` lùi | `latest_published` 2026-07-22 → 2026-06-12; row count vẫn PASS (22). Cả 10 câu mất ground truth → hit rate 1.00 → 0.00 | Dựng lại từ `crossref_records.json` |
| `blank_summary` | Summary → chuỗi rỗng | 3 | GX độ dài summary FAIL | FAIL, 4 dòng vi phạm (3 + 1 bản nhân đôi của dòng bị xóa) | như trên |
| `inject_text_noise` | Chèn token rác vào summary, tạo lại `text_for_embedding` | 3 | Không expectation nào bắt | Không có tín hiệu GX; không quan sát được trên metric vì ground truth của test set đã bị bỏ ở bước 1 | như trên |
| `truncate_title` | Cắt title còn 7 ký tự | 3 | Không (title vẫn not-null) | Không có tín hiệu GX; không quan sát được trên metric (như trên) | như trên |
| `stale_date` | Lùi `published` 5 năm, cộng tương ứng vào `age_days` | 7 | Freshness STALE | 8/22 = 36.4% stale → STALE. `eval_005` trả lời ngày `2021-06-02` lấy từ một bài bị lùi ngày | như trên |
| `duplicate_rows` | Nhân đôi dòng | 3 | GX unique FAIL | FAIL, 6 dòng trùng `paper_id`; 8/10 câu có một `paper_id` xuất hiện 2 lần trong top-4, chiếm chỗ của tài liệu khác | như trên |

Corruption log:

- Đường dẫn: `data/results/corruption_log.json`
- Trạng thái: Có
- Nhận xét: Log ghi `seed=42`, `input_rows=24`, `output_rows=22` và 6 bước. Mỗi bước có mô tả, số dòng và danh sách `paper_id` bị tác động; các bước sửa giá trị ghi thêm giá trị gốc và giá trị mới (vd. `original_titles`/`truncated_titles`, `original_published`/`corrupted_published`). Nhờ đó nhóm đối chiếu được từng câu hỏi bị lỗi nào tác động (bảng trên).

Cách repair đảm bảo dữ liệu được phục hồi từ nguồn đáng tin cậy:

Repair **không vá** bảng corrupted (vd. `drop_duplicates`, điền summary). Vá không lấy lại được 5 bài đã mất, tiêu đề đã bị cắt hay ngày gốc. Thay vào đó, `corruption_flow.py` đọc lại `data/raw/crossref_records.json` (bản raw không bị động tới) và chạy lại đúng `build_clean_dataframe` như baseline. Kết quả được kiểm chứng ba lớp: quality gate PASS 6/6, freshness FRESH, và `_matches_baseline` so sánh 7 cột nội dung với bảng baseline (bỏ `age_days` vì phụ thuộc ngày chạy) → `identical to baseline=True`. Chạy lại bao nhiêu lần cũng cho cùng kết quả (idempotent).

## 10. So sánh baseline, corrupted và repaired

| Metric/signal            | Baseline | Corrupted | Repaired | Thay đổi do corruption | Mức phục hồi | Nhận xét   |
| ------------------------ | -------: | --------: | -------: | -----------------------: | --------------: | ------------ |
| `retrieval_hit_rate`   |     1.00 |      0.00 |     1.00 |                    −1.00 |            100% | Mọi ground truth nằm trong 5 bài bị bỏ |
| `mean_token_f1`        |     1.00 |      0.51 |     1.00 |                    −0.49 |            100% | Không về 0 vì câu trả lời từ bài khác vẫn trùng một phần token; theo dạng: date 0.00, multi_hop 0.36, authors 0.50, summary 0.70, category 1.00 |
| `judge_accuracy`       |     1.00 |      0.60 |     1.00 |                    −0.40 |            100% | Cả 3 trạng thái đều do Gemini chấm (0/10 heuristic) nên so sánh được; nhưng judge chấm đúng cả 2 câu có chuỗi rác (`eval_002`, `eval_009`) |
| `mean_judge_score`     |     5.00 |      3.40 |     5.00 |                    −1.60 |            100% | |
| Quality checks pass/fail |  6/6 PASS |  4/6 (FAIL) |  6/6 PASS |               −2 expectation |            100% | FAIL: unique `paper_id` (6), độ dài summary (4) |
| Freshness status         | FRESH (4.2%) | STALE (36.4%) | FRESH (4.2%) |  +32.2 điểm % stale |            100% | Do `stale_date` (7 dòng) |

Kết luận nhân quả, có artifact hỗ trợ:

1. **Bỏ 5 bài mới nhất + lùi ngày 7 bài + nhân đôi 3 dòng + xóa 3 summary** (`corruption_log.json`) → quality gate FAIL (unique 6, độ dài summary 4) và freshness STALE 36.4% (`corrupted_quality_report.json`, `corrupted_freshness_report.json`) → hit rate 1.00 → 0.00, token F1 1.00 → 0.51, judge accuracy 1.00 → 0.60 (`corrupted_metrics.json`). Agent không báo lỗi nào: nó vẫn trả lời, chỉ là trả lời bằng tài liệu sai (silent failure).
2. **Dựng lại từ `crossref_records.json` bằng cùng code làm sạch** → gate PASS 6/6, freshness FRESH 4.2%, nội dung trùng khớp baseline (`repaired_quality_report.json`, log `identical to baseline=True`) → cả 4 chỉ số về đúng mức baseline (`repaired_metrics.json`).

Kết quả khác kỳ vọng và cách nhóm kiểm tra:

- **Hit rate về 0.00, không phải giảm một phần.** Nhóm map `ground_truth_doc_ids` trong `corrupted_answers.json` với `paper_ids` trong `corruption_log.json`: cả 10 câu có ground truth thuộc 5 bài bị `drop_latest_records` bỏ. `testset.py` sinh câu hỏi từ `df.iloc[0..4]`, tức 5 bài mới nhất. Vì vậy **không kết luận** được tác động riêng của `inject_text_noise` và `truncate_title` lên metric trong lần chạy này: bài bị hai lỗi đó tác động không có trong test set.
- **Câu `category` "đúng" dù tìm sai tài liệu.** `eval_007`, `eval_008` có hit = False nhưng F1 = 1.00 và judge chấm đúng: tài liệu đứng đầu (bài khác) có cùng chuyên ngành với bài được hỏi. Đây là silent failure mà metric câu trả lời không phát hiện được, chỉ retrieval hit (và quality gate) cho thấy vấn đề.
- **Dòng trùng chiếm chỗ trong top-k.** 8/10 câu corrupted có một `paper_id` lặp 2 lần trong top-4, tức top-k thực tế chỉ còn 3 tài liệu khác nhau.
- **LLM judge chấm quá dễ dãi.** `eval_002` và `eval_009` được Gemini chấm đúng với điểm 5/5, dù câu trả lời lấy từ bài bị `inject_text_noise` và chứa chuỗi rác (`An extended [1*[~70z6<6 empirical study on 2w…`). Hai câu này không hit và F1 chỉ 0.67. Như vậy judge accuracy corrupted 0.60 đang đánh giá **cao hơn** thực tế; hit rate và token F1 phản ánh thiệt hại sát hơn.

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** Sau khi merge PR #5 (nhánh RAG) vào `main`, mọi lệnh đều crash ngay khi import:
  ```text
  TypeError: non-default argument 'baseline_metrics' follows default argument 'test_set_json'
  ```
  Sửa lỗi này xong thì xuất hiện lỗi tiếp theo: `ImportError: cannot import name 'repair_clean_dataset' from 'ingestion.cleaning'` (và `save_clean_dataframe`, `CLEAN_COLUMNS`, `build_text_for_embedding`).
- **Nguyên nhân:**
  1. Hai nhánh cùng thêm `test_set_json` vào `Paths`: một bên là field của dataclass, bên kia là `@property`. Sau merge cả hai cùng tồn tại; dataclass coi property là giá trị mặc định của field, nên các field bắt buộc phía sau vi phạm quy tắc "non-default sau default".
  2. PR #5 thay nguyên 9 file trong `src/` bằng phiên bản của nhánh RAG (`git diff d6927bd abda98b --stat -- src`), ghi đè code đã merge trước đó của Data Foundation (`cleaning.py`, `crossref.py`). `ingestion/__init__.py`, `corruption.py`, `corruption_flow.py` vẫn import các hàm không còn tồn tại.
  3. Hai module đọc sai khóa của nhau: `quality.py` trả `expectations` / `expectation_type`, nhưng `corruption_flow.py` đọc `checks` và `reporting.py` đọc `expectation`. Ngoài ra `quality.py` ghi mọi `report_name` khác `baseline` vào `corrupted_quality_report.json`, nên report repaired ghi đè report corrupted.
- **Cách xử lý:** Giữ code đang có trên `main`, chỉ bổ sung phần thiếu:
  - Xóa `@property test_set_json` trùng lặp (giữ field).
  - Khôi phục `save_clean_dataframe`, `repair_clean_dataset` từ commit của Data Foundation (`137c799`) vào `cleaning.py`; thêm `CLEAN_COLUMNS`, `build_text_for_embedding` theo đúng định dạng văn bản hiện tại.
  - Sửa `corruption_flow.py` đọc `expectations`/`expectation_type`, bỏ tham số `generate_corruption_report` không còn nhận.
  - `quality.py` ghi `<report_name>_quality_report.json`; `reporting.py` đọc `expectation_type`.
- **Cách xác minh:** Import toàn bộ package (`core`, `ingestion`, `observability`, `evaluation`, `retrieval`, `pipelines`) → OK. `run_phase1.py` và `run_corruption_flow.py` chạy EXIT=0 (mục 4). `data/quality/` có đủ `baseline_`, `corrupted_`, `repaired_quality_report.json`, trong đó corrupted `success=false` và repaired `success=true`.

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng   | Hướng cải thiện có thể kiểm chứng |
| --------------------- | -------------- | ----------------------------------------- |
| Test set sinh từ 5 bài mới nhất (`df.iloc[0..4]`) | `drop_latest_records` xóa toàn bộ ground truth, che tác động riêng của noise/truncate title; hit rate corrupted bị ép về 0.00 | Chọn 10 bài rải đều từ mới → cũ. Kiểm chứng: `by_question_type` của corrupted phân biệt được từng loại lỗi (không còn đồng loạt miss), và có câu hỏi trỏ tới bài trong nhóm `inject_text_noise` / `truncate_title` của log |
| LLM judge dễ dãi với câu trả lời chứa ký tự rác | `eval_002`, `eval_009` corrupted chứa chuỗi rác vẫn được chấm 5/5, nên judge accuracy corrupted (0.60) cao hơn thực tế | Thêm yêu cầu trong prompt judge: câu trả lời chứa chuỗi vô nghĩa hoặc thuộc bài khác thì `correct=false`. Kiểm chứng: 2 câu này bị chấm sai, judge accuracy corrupted ≤ 0.40 |
| Judge LLM dùng Gemini free-tier (giới hạn 20 request/ngày/model) | Khi hết quota, judge chuyển sang heuristic và judge accuracy giữa các lần chạy không so sánh được (lần chạy trước đó: 7/10, 0/10, 4/10 câu heuristic) | Cache verdict theo `(question, answer)` hoặc chạy cả 3 trạng thái với `LLM_PROVIDER=mock`. Kiểm chứng: `judge_fallback_count` bằng nhau ở 3 file metrics |
| `phase1.py` chỉ in trạng thái quality gate, không dừng khi FAIL | Dữ liệu bẩn ở Pha 1 vẫn được index vào `papers-baseline` | Dừng pipeline (`raise`) khi `quality["success"]` là `False`, trước bước index. Kiểm chứng: chạy Pha 1 với bảng có dòng trùng → dừng ở bước 3, collection không được tạo lại |
| Gate bỏ lọt summary `None` và title chuỗi rỗng | Negative test ngày 2026-09-25: `summary = None` → PASS, `title = ""` → PASS (chỉ `summary = ""` bị bắt) | Thêm `ExpectColumnValuesToNotBeNull(summary)` và đổi title toàn khoảng trắng thành `None` trước khi validate. Kiểm chứng: 3 phép thử đều FAIL, dữ liệu sạch vẫn PASS 6/6 |
| Câu `multi_hop` chỉ có ground truth từ một bài | Baseline multi_hop đạt F1 = 1.00 mà không cần tổng hợp hai tài liệu | Ghép câu đầu summary của cả hai bài làm `ground_truth`. Kiểm chứng: F1 baseline của multi_hop phản ánh việc QA chỉ trích một tài liệu (< 1.00) |
| `drop_latest_records` không làm FAIL expectation nào (22 vẫn trong 5–5000) | Mất dữ liệu tươi chỉ lộ qua freshness | Thêm expectation so với lần chạy trước: số dòng không giảm > 5%, `max(published)` không lùi. Kiểm chứng: FAIL ở corrupted, PASS ở baseline/repaired |
| Chroma để lại thư mục segment mồ côi sau mỗi lần xóa/tạo lại collection | `data/chroma` hiện có 21 thư mục segment, chỉ 3 thư mục còn được `chroma.sqlite3` tham chiếu; dung lượng repo tăng theo số lần chạy | Dọn các thư mục không có trong bảng `segments` sau khi build. Kiểm chứng: sau 2 lần chạy liên tiếp vẫn đúng 3 thư mục |
| Chế độ live API ghi đè snapshot ngay khi HTTP 200, trước khi parse | Payload rỗng/lỗi có thể thay mất raw snapshot dùng để repair | Chỉ ghi snapshot khi parse được ≥ 1 record. Kiểm chứng: giả lập payload rỗng → snapshot giữ nguyên |

## 13. Checklist trước khi nộp

- [ ] Thông tin nhóm và repository chính xác.
- [ ] Phân công khớp với module, artifact và kết quả thực tế.
- [ ] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp.
- [ ] Baseline, corrupted và repaired dùng cùng evaluation set.
- [ ] Bảng metrics khớp với các file trong `data/results/`.
- [ ] Quality/freshness conclusions khớp với `data/quality/`.
- [ ] Các đường dẫn báo cáo và artifact truy cập được.
- [ ] Mỗi thành viên đã hoàn thành báo cáo vai trò riêng.
- [ ] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh.
