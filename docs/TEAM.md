# Danh Sách Thành Viên & Báo Cáo Phân Công Nhóm

- **Tên Nhóm:** `120YenLang`
- **Mã Nhóm / Lớp:** `K4-L3-DAY10`
- **Tên Repository Nộp Bài:** `K4-L3-DAY10-120YenLang-DataPipeline`

---

## # Thành viên

Nhóm 5 người: vai trò "Observability & Evaluation" được tách làm hai (4a giám sát chất lượng + tiêm lỗi, 4b đánh giá + báo cáo) để mỗi người sở hữu một nhóm file riêng.

| STT | Họ và tên | MSSV | Email | Vai trò & Phân công công việc | Báo cáo cá nhân |
|---:|---|---|---|---|---|
| 1 | Nguyễn Đức Thắng | 2A202602605 | | **Pipeline Lead** (`core/config.py`, `pipelines/phase1.py`, `pipelines/corruption_flow.py`, `script/`, tích hợp & debug end-to-end) | `report/2A202602605_NguyenDucThang.md` |
| 2 | | | | **Data Foundation Owner** (`ingestion/crossref.py`, `ingestion/cleaning.py`, raw snapshot, repair từ raw) | `report/<MSSV2>_HoTen.md` |
| 3 | | | | **RAG Specialist** (`retrieval/index.py`, `retrieval/embeddings.py`, `retrieval/qa.py`, `retrieval/agent.py`, `retrieval/llm.py`, ChromaDB) | `report/<MSSV3>_HoTen.md` |
| 4 | | | | **Observability Lead** (`observability/quality.py` GX 1.x, Freshness SLA, `ingestion/corruption.py`) | `report/<MSSV4>_HoTen.md` |
| 5 | | | | **Evaluation & Reporting Lead** (`evaluation/testset.py`, `evaluation/metrics.py`, `observability/reporting.py`) | `report/<MSSV5>_HoTen.md` |

**Luồng bàn giao giữa các vai trò:** (2) raw → clean dataframe → (4) quality gate → (3) Chroma index → (5) test set + metrics + report. (1) nối tất cả trong `phase1.py` / `corruption_flow.py` và chốt contract (tên cột, đường dẫn artifact) giữa các module.

---

## # Cá nhân

### ## NguyenDucThang-2A202602605
- **Vai trò:** Pipeline Lead (Trưởng nhóm & Điều phối Pipeline).
- **Công việc chi tiết đã hoàn thành:**
  - Kết nối luồng Pha 1 trong `src/pipelines/phase1.py` (ingest → clean → quality gate → index → test set → evaluate → agent demo → report), quality gate FAIL thì dừng trước khi index.
  - Kết nối luồng corruption → evaluate → repair → compare trong `src/pipelines/corruption_flow.py`, kiểm tra repair có trùng khớp baseline.
  - Bổ sung alias đường dẫn `paths.test_set_json` trong `core/config.py` cho lệnh kiểm tra của hướng dẫn.
  - Debug tích hợp: pipeline treo ở bước evaluate (Gemini không có timeout, HuggingFace Hub HEAD request) → thêm timeout/retry trong `retrieval/llm.py`, load model từ cache local trong `retrieval/embeddings.py`.
- **Điều học được / Đóng góp chính:**
  - Idempotent repair từ raw snapshot, và việc mọi lời gọi mạng trong pipeline đều cần timeout.

### ## HoVaTen2-MSSV2
- **Vai trò:** Phụ trách Ingestion, Làm sạch & Phục hồi dữ liệu.
- **Công việc chi tiết đã hoàn thành:**
  - Xây dựng module thu thập Crossref API với cơ chế Fallback offline trong `src/ingestion/crossref.py`.
  - Chuẩn hóa schema, tính toán trường `age_days` và `text_for_embedding` trong `src/ingestion/cleaning.py`.
  - Thực thi cơ chế Idempotent Repair phục hồi dữ liệu từ raw snapshot.
- **Điều học được / Đóng góp chính:**
  - Kỹ thuật truy vết nguồn gốc dữ liệu (Data Lineage) và bảo toàn raw snapshot trước khi biến đổi.

### ## HoVaTen3-MSSV3
- **Vai trò:** Phụ trách RAG, Vector Database & Embedding.
- **Công việc chi tiết đã hoàn thành:**
  - Quản lý mô hình embedding `sentence-transformers/all-MiniLM-L6-v2`.
  - Nạp và quản lý 3 collection riêng biệt trong ChromaDB (`papers-baseline`, `papers-corrupted`, `papers-repaired`).
  - Xây dựng QA Agent truy vấn ngữ cảnh chính xác theo tài liệu.
- **Điều học được / Đóng góp chính:**
  - Cách cô lập các không gian vector để so sánh khách quan giữa dữ liệu sạch và dữ liệu bị lỗi.

### ## HoVaTen4-MSSV4
- **Vai trò:** Observability Lead.
- **Công việc chi tiết đã hoàn thành:**
  - Thiết lập Quality Gate theo chuẩn mới **Great Expectations 1.x** và giám sát Freshness SLA trong `src/observability/quality.py`.
  - Xây dựng 6 kịch bản tiêm lỗi có seed cố định trong `src/ingestion/corruption.py`.
- **Điều học được / Đóng góp chính:**
  - Cách thiết lập hệ thống cảnh báo sớm chặn đứng hiện tượng Silent Failure trước khi dữ liệu vào serving layer.

### ## HoVaTen5-MSSV5
- **Vai trò:** Evaluation & Reporting Lead.
- **Công việc chi tiết đã hoàn thành:**
  - Xây dựng bộ 10 câu hỏi đánh giá (5 dạng, có `multi_hop`) trong `src/evaluation/testset.py`.
  - Chỉ số theo dạng câu hỏi và đếm số câu judge phải dùng heuristic trong `src/evaluation/metrics.py`.
  - Xuất `phase1_report.md` và bảng đối chiếu 3 trạng thái `corruption_report.md` trong `src/observability/reporting.py`.
- **Điều học được / Đóng góp chính:**
  - Vì sao phải dùng cùng một test set cố định để so sánh baseline / corrupted / repaired.
