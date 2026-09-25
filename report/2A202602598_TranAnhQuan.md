# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Trần Anh Quân             |
| MSSV               | 2A202602598                |
| Khóa/Lớp         | K4                         |
| Tên nhóm         | 120YenLang              |
| Vai trò chính    | Data Foundation & Recovery Owner |
| Repository         | https://github.com/TaiHoang2501/K4A-DAY10-120YenLang |
| Ngày hoàn thành | 2026-09-25                 |

---

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao  | Trạng thái |
| ------------------ | --------------------- | ---------------- | ----------------- | :----------: |
| **Raw Data Ingestion & Lineage** | `src/ingestion/crossref.py` (`parse_crossref_payload`, `fetch_source_records`, `load_raw_records`) | Crossref REST API response payload hoặc file snapshot `data/raw/crossref_response.json` | Danh sách đối tượng `PaperRecord`, lưu file `data/raw/crossref_records.json` | **Hoàn thành** |
| **Data Cleaning & Transformation** | `src/ingestion/cleaning.py` (`build_clean_dataframe`, `save_clean_dataframe`) | Danh sách `PaperRecord`, đối tượng thời gian chạy `run_date` | DataFrame chuẩn hóa, xuất ra `data/clean/papers_clean.csv` và `papers_clean.json` | **Hoàn thành** |
| **Idempotent Repair Flow** | `src/ingestion/cleaning.py` (`repair_clean_dataset`) | `Settings` cấu hình hệ thống, kho `data/raw/` nguyên bản | Tái tạo và khôi phục đồng nhất `data/clean/papers_clean.*` và `data/clean/papers_clean_repaired.*` | **Hoàn thành** |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --------- | ----------------------------- | ------- |
| **Cung cấp Data Contract cho Quality Gate** | Member 4 (`src/observability/quality.py`) | Thống nhất cấu trúc DataFrame có các cột `paper_id`, `title`, `summary`, `text_for_embedding`, `age_days` giúp Great Expectations 1.x validation đạt `success=True`. |
| **Cung cấp cấu trúc văn bản tạo Vector** | Member 3 (`src/retrieval/index.py`) | Cung cấp trường `text_for_embedding` gồm 5 phần chuẩn giúp ChromaDB đánh chỉ mục collection `papers-baseline` thành công với 24 vector. |

---

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --------------------- | --------------------------- | ---------------- | ------------- |
| Ingestion dữ liệu học thuật với cơ chế Dual-mode | `src/ingestion/crossref.py` | Tải và phân tích 24 bài báo khoa học, lưu trữ 2 artifacts: `data/raw/crossref_response.json` và `crossref_records.json` | Chạy lệnh kiểm tra Ingestion in ra: `Tín hiệu hoàn thành: Đã tải 24 bài báo` |
| Làm sạch và chuẩn hóa ngữ cảnh nhúng vector | `src/ingestion/cleaning.py` | Tạo thành công 24 bản ghi sạch, khử trùng lặp 100%, tạo trường `text_for_embedding` và tính `age_days` | Chạy lệnh kiểm tra Cleaning in ra: `Tín hiệu hoàn thành: Clean thành công 24 dòng` |
| Thiết lập cơ chế tự phục hồi dữ liệu Idempotent | `src/ingestion/cleaning.py` (`repair_clean_dataset`) | Khôi phục hệ thống về trạng thái ban đầu từ raw snapshot, chạy lặp lại nhiều lần vẫn đạt kết quả nhất quán | Chạy lệnh repair và đối chiếu với bản gốc |

### Output cụ thể tạo ra và bàn giao:
- File dữ liệu sạch [data/clean/papers_clean.csv](../data/clean/papers_clean.csv) và [data/clean/papers_clean.json](../data/clean/papers_clean.json) gồm đúng 24 bản ghi nghiên cứu khoa học, sạch hoàn toàn các thẻ HTML/JATS XML rác, có cột `age_days` và `text_for_embedding` hoàn chỉnh.

---

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết
1. **Dữ liệu thô chứa nhiều nhiễu:** Dữ liệu trả về từ Crossref API chứa các thẻ JATS XML (như `<jats:p>`, `</jats:p>`, `<i>`, `<b>`), khoảng trắng thừa và ký tự HTML entities (`&amp;`, `&lt;`). Nếu đưa thẳng vào Vector DB, các thẻ rác này sẽ làm sai lệch vector embedding của mô hình `all-MiniLM-L6-v2`.
2. **Nguy cơ gián đoạn do mạng/API:** Crossref API công khai thường xuyên gặp mã lỗi `429 Too Many Requests` hoặc rớt mạng phòng lab, khiến pipeline dừng đột ngột.
3. **Hiện tượng Silent Failure do dữ liệu mồ côi/trùng lặp:** Cùng một bài báo bị nạp nhiều lần gây phân mảnh vector; dữ liệu quá cũ (`age_days` cao) khiến Agent tư vấn sai mà không báo lỗi đỏ.
4. **Yêu cầu Idempotent:** Cần một cơ chế phục hồi mà khi dữ liệu bị tiêm lỗi, pipeline có thể tái tạo lại bản sạch 100% tự động mà không cần can thiệp thủ công.

### Cách triển khai
> Lưu ý: sau khi merge PR #5, `crossref.py` và phần `build_clean_dataframe` trong `cleaning.py` trên `main` là phiên bản từ nhánh RAG, khác bản tôi commit ở `137c799`. `save_clean_dataframe` và `repair_clean_dataset` của tôi đã được khôi phục từ `137c799`. Mô tả dưới đây theo code hiện tại.

1. **Bóc tách và làm sạch text:** `_strip_tags()` dùng regex `<[^>]+>` xóa toàn bộ thẻ XML/HTML (`<jats:p>`, `</jats:p>`, `<b>`…), sau đó `normalize_whitespace()` chuẩn hóa khoảng trắng. DOI được `strip()` và chuyển chữ thường.
2. **Cơ chế Dual-mode Ingestion:** Trong `fetch_source_records()`, nếu `refresh_source=False` (mặc định) thì đọc thẳng snapshot local `data/raw/crossref_response.json`. Khi `REFRESH_SOURCE=1`: gọi API (timeout 30 giây), gặp 429/503 thì chuyển ngay sang snapshot, lỗi mạng hoặc mã lỗi khác thì thử tối đa 3 lần rồi mới chuyển.
3. **Tính toán độ tươi dữ liệu (`age_days`):** `(run_date.date() - published_dt.date()).days`, với `published_dt` parse từ chuỗi `YYYY-MM-DD` (`_safe_parse_date`). Ngày không parse được thì `age_days = None`.
4. **Ghép nối cấu trúc 5 phần `text_for_embedding`:**
   ```text
   Title: <Tiêu đề>
   Authors: <Danh sách tác giả>
   Published: <Ngày xuất bản>
   Categories: <Chuyên ngành>
   Summary: <Tóm tắt nội dung>
   ```
5. **Khử trùng lặp, lọc và sắp xếp:** `df.drop_duplicates(subset=["paper_id"], keep="first")`, loại dòng thiếu cả title lẫn summary, rồi sắp xếp theo `published` giảm dần. Cùng input thì cùng output, nên repair chạy lại nhiều lần vẫn cho một kết quả.

### Input, output và contract

| Thành phần | Mô tả |
| ---------- | ----- |
| **Input** | Snapshot JSON `data/raw/crossref_response.json` (dict chứa `message.items`), tham số `run_date: datetime` |
| **Output** | `pd.DataFrame` 16 cột: `paper_id`, `title`, `summary`, `authors`, `authors_joined`, `categories`, `categories_joined`, `primary_category`, `published`, `updated`, `age_days`, `summary_chars`, `abs_url`, `pdf_url`, `comment`, `text_for_embedding` |
| **Module phụ thuộc** | `src/core/config.py` (cung cấp Paths và cấu hình Settings) |
| **Module sử dụng output** | `src/observability/quality.py` (kiểm tra 4 Expectations GX 1.x & Freshness), `src/retrieval/index.py` (ChromaDB Indexing) |
| **Điều kiện lỗi cần xử lý** | Mất mạng/API quá tải (chuyển fallback snapshot), DOI rỗng (bỏ qua), thiếu cả title lẫn abstract (bỏ qua), `date-parts` thiếu tháng/ngày (điền 01), bài báo không có ngày xuất bản (`age_days = None`), thẻ XML lồng nhau |

### Cách xác minh

```bash
# 1. Xác minh Ingestion
python -c "from core.config import load_settings; from ingestion.crossref import fetch_source_records; s=load_settings(); r=fetch_source_records(s); print(f'Tín hiệu hoàn thành: Đã tải {len(r)} bài báo')"

# 2. Xác minh Cleaning & Transformation
python -c "from datetime import datetime, timezone; from core.config import load_settings; from ingestion.crossref import load_raw_records; from ingestion.cleaning import build_clean_dataframe; s=load_settings(); df=build_clean_dataframe(load_raw_records(s.paths.raw_records_json), datetime.now(timezone.utc)); print(f'Tín hiệu hoàn thành: Clean thành công {len(df)} dòng')"
```

- **Kết quả mong đợi:** In ra `Tín hiệu hoàn thành: Đã tải 24 bài báo` và `Tín hiệu hoàn thành: Clean thành công 24 dòng`.
- **Kết quả thực tế:** Console in ra chính xác 2 dòng thông báo trên với mã thoát 0.
- **Artifact:** `data/raw/crossref_records.json`, `data/clean/papers_clean.csv`, `data/clean/papers_clean.json`.

---

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Khi thiết kế hàm `fetch_source_records()`, cần quyết định xem có nên luôn luôn gọi live API ra ngoài Internet hay không.
- **Các phương án đã cân nhắc:**
  1. *Phương án A:* Luôn gọi trực tiếp Crossref REST API. Nếu thất bại thì báo lỗi và dừng toàn bộ pipeline.
  2. *Phương án B:* Thiết kế cơ chế **Dual-mode Fallback**: Ưu tiên đọc từ live API nếu được yêu cầu, nhưng khi gặp bất kỳ sự cố mạng hoặc lỗi `429/503`, tự động phục hồi chuyển sang đọc file snapshot chuẩn `data/raw/crossref_response.json`.
- **Phương án đã chọn:** Phương án B.
- **Lý do:** Trade-off giữa "dữ liệu luôn mới nhất" và "tính ổn định/tái lập (reproducibility) trong môi trường phòng lab". Crossref API có rate limit rất chặt chẽ, việc nhiều sinh viên cùng gọi đồng thời trong phòng lab chắc chắn dẫn tới lỗi `429`. Phương án B đảm bảo Data Lineage luôn được bảo toàn và pipeline không bao giờ bị nghẽn bất chợt.
- **Bằng chứng:** Pipeline chạy mượt mà ngay cả khi ngắt kết nối Internet, nạp đủ 24 bài báo mà không phát sinh bất kỳ ngoại lệ nào.

---

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:**
  ```text
  UnicodeEncodeError: 'charmap' codec can't encode character '\u1ec7' in position 6: character maps to <undefined>
  ModuleNotFoundError: No module named 'core'
  ```
- **Lệnh tái hiện:** Chạy lệnh `python -c "..."` trên terminal PowerShell mặc định của Windows.
- **Nguyên nhân gốc:**
  1. Terminal PowerShell trên Windows mặc định dùng bảng mã `cp1252`, không hỗ trợ ký tự UTF-8 tiếng Việt (`\u1ec7` trong chữ "hiệu").
  2. Biến môi trường `PYTHONPATH` chưa trỏ vào thư mục `src`, khiến Python không tìm thấy module `core`.
- **Cách xử lý:**
  1. Thêm biến môi trường trước khi chạy lệnh: `$env:PYTHONIOENCODING="utf-8"`.
  2. Cấu hình `$env:PYTHONPATH="src"` (hoặc cài đặt editable package qua `pip install -e .`).
- **Cách xác minh sau khi sửa:** Chạy lại lệnh nghiệm thu, console in ra trơn tru chuỗi: `Tín hiệu hoàn thành: Clean thành công 24 dòng`.
- **Điều học được:** Khi phát triển pipeline trên môi trường đa nền tảng (Windows/Linux), luôn phải chủ động cấu hình encoding UTF-8 và quản lý biến môi trường chặt chẽ.

---

## 7. Hiểu biết về luồng end-to-end

1. **Dữ liệu đi từ Crossref đến vector index như thế nào?**
   - Dữ liệu thô dạng JSON được kéo về từ Crossref API $\rightarrow$ lưu snapshot nguyên gốc vào `data/raw/crossref_response.json` (bảo toàn lineage) $\rightarrow$ parse thành `PaperRecord` lưu vào `crossref_records.json` $\rightarrow$ qua `cleaning.py` để loại bỏ thẻ JATS XML, chuẩn hóa khoảng trắng, tính `age_days`, tạo cột `text_for_embedding` $\rightarrow$ lưu ra `papers_clean.csv` $\rightarrow$ qua `quality.py` kiểm định Great Expectations $\rightarrow$ nạp vào ChromaDB với mô hình embedding `all-MiniLM-L6-v2` để lưu vector và metadata.

2. **Evaluation set và ground-truth document IDs dùng để đo retrieval/answer quality ra sao?**
   - Test set chứa 10 câu hỏi nghiệp vụ cùng đáp án mẫu (`ground_truth`) và danh sách DOI bài báo chứa thông tin chuẩn (`ground_truth_doc_ids`).
   - `retrieval_hit_rate`: Đo tỷ lệ câu hỏi mà ChromaDB truy xuất được ít nhất 1 tài liệu nằm trong `ground_truth_doc_ids` (đo độ chính xác của bộ tìm kiếm).
   - `mean_token_f1`: Đo độ trùng khớp từng từ giữa câu trả lời sinh ra từ LLM và `ground_truth` (đo chất lượng câu trả lời).

3. **Quality checks khác freshness monitoring ở điểm nào trong bài lab?**
   - **Quality checks (Great Expectations 1.x):** Kiểm tra tính toàn vẹn cấu trúc và nội dung tĩnh của dữ liệu (số dòng trong khoảng 5-5000, không bị null cột chính, `paper_id` là duy nhất, độ dài tóm tắt $\ge 30$ ký tự).
   - **Freshness monitoring:** Giám sát khía cạnh thời gian và độ trễ (temporal dimension). Dữ liệu có thể rất sạch và chuẩn format nhưng nếu quá hạn (`age_days > 180`), nó sẽ làm Agent đưa ra thông tin lỗi thời.

4. **Vì sao phải dùng cùng test set cho baseline, corrupted và repaired?**
   - Để đảm bảo tính khách quan và khoa học của phương pháp thực nghiệm (controlled experiment). Cố định đề thi giúp loại bỏ biến số ngẫu nhiên; mọi sự sụt giảm hay phục hồi của điểm số chỉ đến từ sự biến thiên của chất lượng dữ liệu.

5. **Repair được xem là thành công dựa trên artifact và metric nào?**
   - **Artifact:** Tái tạo thành công `papers_clean.csv` và `papers_clean_repaired.csv` có 24 dòng sạch, khớp hoàn toàn với snapshot gốc `data/raw/`.
   - **Metric:** Quality Gate chuyển từ FAILED về lại PASSED; Freshness SLA đạt 100% compliant; `retrieval_hit_rate` và `mean_token_f1` phục hồi về bằng hoặc xấp xỉ mức Baseline ban đầu.

---

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ------------- | -------: | --------: | -------: | --------------------- |
| `retrieval_hit_rate` | 1.00 | 0.00 | 1.00 | Cả 10 câu hỏi về 5 bài mới nhất, đúng 5 bài bị `drop_latest_records` bỏ, nên không câu nào tìm được bài đúng; sau khi repair từ raw, hit rate về 1.00. |
| `mean_token_f1` | 1.00 | 0.51 | 1.00 | Câu trả lời lấy từ bài khác (có bài bị chèn rác hoặc lùi ngày) nên F1 giảm một nửa; sau repair phục hồi hoàn toàn. |
| `judge_accuracy` | 1.00 | 0.60 | 1.00 | Cả 3 trạng thái do Gemini chấm (0/10 câu heuristic). Judge vẫn chấm đúng một số câu lấy từ bài sai, nên 0.60 cao hơn thực tế. |
| `mean_judge_score` | 5.00 | 3.40 | 5.00 | Agent vẫn trả lời trôi chảy trên dữ liệu bẩn (Silent Failure). |
| Quality checks | PASSED (6/6) | FAILED (4/6) | PASSED (6/6) | GX 1.x bắt được trùng lặp `paper_id` (6 dòng) và summary < 30 ký tự (4 dòng) trên tập Corrupted. |
| Freshness status | FRESH (1/24 = 4.2%) | STALE (8/22 = 36.4%) | FRESH (1/24 = 4.2%) | Kịch bản lùi ngày xuất bản 7 bài vượt ngưỡng SLA 25%. |

Số liệu từ lần chạy 2026-09-25 10:10–10:11Z (`data/results/*_metrics.json`, `data/quality/*.json`).

### Kết luận từ số liệu
1. **Chuỗi 1:** `Data corruption (bỏ 5 bài mới nhất, xóa 3 summary, nhân đôi 3 dòng, lùi ngày 7 bài)` $\rightarrow$ `GX 1.x báo FAILED (unique paper_id, summary length < 30), Freshness STALE 36.4%` $\rightarrow$ `Retrieval Hit Rate rơi từ 1.00 xuống 0.00, Token F1 từ 1.00 xuống 0.51`.
2. **Chuỗi 2:** `Idempotent Repair (đọc lại từ data/raw/crossref_records.json)` $\rightarrow$ `Quality check trở lại PASSED 6/6, Freshness FRESH 4.2%, nội dung trùng khớp baseline (identical to baseline=True)` $\rightarrow$ `Hit Rate và Token F1 lấy lại 100% phong độ ban đầu (1.00 / 1.00)`.

- **Corruption ảnh hưởng rõ nhất:** Lỗi **Drop latest records**. Toàn bộ `ground_truth_doc_ids` của 10 câu hỏi nằm trong 5 bài bị bỏ (đối chiếu `corruption_log.json` với `corrupted_answers.json`). Đây là lỗi *mất* dữ liệu, không vá được trên bảng hiện có, nên repair bắt buộc phải đọc lại từ raw snapshot.
- **Kết quả bất ngờ:** Dù dữ liệu bị tiêm lỗi nặng, Agent vẫn trả lời câu hỏi rất tự tin và trôi chảy (Silent Failure). Ví dụ `eval_005` trả lời ngày xuất bản `2021-06-02`, lấy từ một bài bị lùi ngày 5 năm. Một số câu còn "đúng" dù tìm sai tài liệu (câu hỏi chuyên ngành, vì bài khác có cùng chuyên ngành), chứng minh Data Observability là tấm khiên bắt buộc phải có trước Vector Store.

---

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất
1. **Về Data Pipeline:** Tính **Idempotent** và **Data Lineage (Bảo toàn Raw Data)** là yếu tố sống còn. Luôn giữ dữ liệu thô nguyên vẹn ở tầng Ingestion làm nguồn chân lý duy nhất (Single Source of Truth) để có thể tái tạo dữ liệu sạch bất cứ lúc nào.
2. **Về Data Quality & Observability:** Không thể chỉ dựa vào log lỗi của ứng dụng để biết hệ thống có khỏe mạnh hay không. Hiện tượng Silent Failure trong AI chỉ có thể bị phát hiện bởi các chốt kiểm dịch tự động như Great Expectations và giám sát độ tươi (Freshness SLA).
3. **Về ảnh hưởng của Data đến RAG:** *"Garbage In, Garbage Out"* – Một mô hình nhúng vector hay LLM tối tân đến đâu cũng hoàn toàn bất lực nếu đầu vào là văn bản rác, thiếu tiêu đề hoặc sai lệch ngày tháng.

### Nếu có thêm thời gian
- Xây dựng thêm một **Auto-Quarantine Mechanism**: Khi Data Quality Gate phát hiện bản ghi lỗi, thay vì dừng toàn bộ batch, pipeline sẽ tự động tách các dòng lỗi vào một bảng cách ly (`data/quarantine/`), chỉ cho phép các dòng sạch đi vào Vector Store, đồng thời bắn cảnh báo qua Webhook/Slack.

---

## 10. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Trần Anh Quân  
**Ngày xác nhận:** 2026-09-25  
