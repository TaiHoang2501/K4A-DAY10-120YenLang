# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Hoàng Anh Tài             |
| MSSV               | 2A202602612                     |
| Khóa/Lớp         | K4              |
| Tên nhóm         | 120YenLang     |
| Vai trò chính    | RAG Specialist (embedding, ChromaDB, QA/agent) |
| Repository         | https://github.com/TaiHoang2501/K4A-DAY10-120YenLang |
| Ngày hoàn thành | 2026-09-25               |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao  | Trạng thái                                 |
| ------------------ | --------------------- | ---------------- | ----------------- | -------------------------------------------- |
| Vector index ChromaDB | `src/retrieval/index.py` — `LocalEmbeddingIndex.__init__()`, `build_from_clean()`, `build()`, `load()`, `_set_documents()` | Clean DataFrame (cột `text_for_embedding` + metadata) | Collection Chroma + manifest `data/embeddings/papers_embeddings*.json` | Hoàn thành |
| Truy vấn ngữ nghĩa | `index.py` — `search()`, `semantic_search()`, `lookup()` | Câu hỏi, `top_k` | `list[SearchResult]` (paper_id, title, score, content, metadata) | Hoàn thành |
| Embedding model | `src/retrieval/embeddings.py` — `MiniLMEmbeddings` | `sentence-transformers/all-MiniLM-L6-v2` | Vector 384 chiều, đã chuẩn hóa | Hoàn thành (dùng sẵn; phần load từ cache do Pipeline Lead sửa) |
| QA & agent | `src/retrieval/qa.py` — `answer_question()`; `src/retrieval/agent.py` — `build_agent()` | Index, câu hỏi | `AnswerResult`; agent LangChain có 2 tool | Hoàn thành (dùng sẵn, kiểm tra tích hợp với test set) |
| 3 collection độc lập | `papers-baseline`, `papers-corrupted`, `papers-repaired` | 3 bảng clean | 24 / 22 / 24 tài liệu | Hoàn thành |

Tôi nhận DataFrame từ Data Foundation (qua quality gate của Observability) và bàn giao index cho Evaluation (`evaluate_pipeline` gọi `answer_question`), cùng agent cho bước demo của Pipeline Lead.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                         | Thành viên/module được hỗ trợ | Kết quả                    |
| ------------------------------------ | ------------------------------------ | ---------------------------- |
| Thống nhất mẫu câu hỏi với logic trích câu trả lời của `qa.py` | Evaluation & Reporting Lead — `evaluation/testset.py` | Câu hỏi dùng đúng cụm `who authored`, `when was … published`, `what categories`, `'<title>'` trong nháy đơn, nên QA đi đúng nhánh trích xuất và tra cứu chính xác theo tiêu đề. 8/8 câu một-bài đạt F1 = 1.00 ở baseline |
| Kiểm tra QA trên toàn bộ test set trước khi chạy pipeline | Evaluation & Reporting Lead | Smoke test: 10/10 hit; multi_hop F1 0.73 (QA chỉ trích từ tài liệu đứng đầu) |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao       | Cách xác minh         |
| --------------------------- | ----------------------------- | ------------------------- | ----------------------- |
| Cho phép tạo index chỉ với `collection_name` (get-or-create, cosine) | `LocalEmbeddingIndex.__init__()` | Lệnh CP2 của hướng dẫn chạy được | Lệnh smoke test ở mục 4 |
| Rebuild collection idempotent: xóa rồi tạo lại, embed, ghi manifest | `build_from_clean()` | Chạy lại bao nhiêu lần cũng cùng một trạng thái | Số tài liệu trong manifest luôn khớp số dòng DataFrame (24 / 22 / 24) |
| Giữ `build()` / `load()` / `search()` tương thích với code cũ | `build()` gọi `build_from_clean()`; `semantic_search()` là tên gọi khác của `search()` | `metrics.py`, `agent.py`, `phase1.py` không phải sửa | Cả `run_phase1.py` và `run_corruption_flow.py` chạy EXIT=0 |
| Tách 3 collection theo đường dẫn manifest | `_derive_collection_name()` | `papers-baseline`, `papers-corrupted`, `papers-repaired` | `chroma.sqlite3` bảng `collections` có đúng 3 tên |

Output cụ thể phần việc của tôi tạo ra:

`data/chroma/` chứa 3 collection. Manifest `data/embeddings/papers_embeddings.json` (24 tài liệu), `papers_embeddings_corrupted.json` (22), `papers_embeddings_repaired.json` (24). Retrieval hit rate trên cùng test set: 1.00 / 0.70 / 1.00.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Index phải tạo được theo hai cách: cách của hướng dẫn CP2 (`LocalEmbeddingIndex(s, collection_name=...)` rồi `build_from_clean()`, `semantic_search()`) và cách mà `metrics.py`/`agent.py` đang dùng (`LocalEmbeddingIndex.build(df, settings)`, `load()`, `search()`). Ngoài ra, ba trạng thái baseline/corrupted/repaired phải nằm trong các không gian vector tách biệt, và mỗi lần chạy lại không được để sót vector cũ.

### Cách triển khai

- **Khởi tạo:** `collection_name` mặc định là `papers-baseline`, `persist_path` mặc định `data/chroma`. Dùng `get_or_create_collection(configuration={"hnsw": {"space": "cosine"}})`, nên tạo index cho collection chưa tồn tại không còn lỗi.
- **Rebuild (`build_from_clean`):** đọc `papers_clean.json` nếu không truyền DataFrame. Xóa collection cũ rồi tạo lại (không upsert), embed toàn bộ `text_for_embedding` một lượt, `add` với `record_id = "{paper_id}::{index}"` (thêm index để dòng trùng `paper_id` trong bảng corrupted vẫn có id riêng), cập nhật bảng tra cứu theo `paper_id`/tiêu đề, ghi manifest.
- **Search:** embed câu hỏi (vector chuẩn hóa), `collection.query` lấy top-k, đổi khoảng cách cosine thành điểm `1 - distance`.
- **QA (`answer_question`):** nếu câu hỏi có `'<title>'` và tiêu đề khớp chính xác thì đưa bài đó lên đầu, rồi trích câu trả lời theo loại câu hỏi từ metadata của tài liệu đứng đầu.

### Input, output và contract

| Thành phần                   | Mô tả                                     |
| ------------------------------ | ------------------------------------------- |
| Input                          | DataFrame có `paper_id, title, text_for_embedding, published, authors_joined, categories_joined, summary, abs_url, pdf_url`; `Settings` (`embedding_model`, `top_k=4`, tên collection) |
| Output                         | Collection Chroma (cosine); manifest JSON `{backend, embedding_model, persist_path, collection_name, documents}`; `SearchResult`; `AnswerResult` |
| Module phụ thuộc             | `retrieval/embeddings.py`, `chromadb` 1.5.9, `sentence-transformers` |
| Module sử dụng output        | `evaluation/metrics.py` (`evaluate_pipeline`), `retrieval/agent.py`, `pipelines/phase1.py`, `pipelines/corruption_flow.py` |
| Điều kiện lỗi cần xử lý | Collection chưa tồn tại; DataFrame rỗng (bỏ qua `add`); `paper_id` trùng trong bảng corrupted; tiêu đề bị cắt (tra cứu chính xác thất bại → dựa vào semantic search) |

### Cách xác minh

```bash
python -c "from core.config import load_settings; from retrieval.index import LocalEmbeddingIndex; s=load_settings(); idx=LocalEmbeddingIndex(s, collection_name='papers-baseline'); idx.build_from_clean(); res=idx.semantic_search('machine learning', top_k=2); print(f'Tín hiệu hoàn thành: Tìm thấy {len(res)} tài liệu liên quan')"
```

- **Kết quả mong đợi:** `Tìm thấy 2 tài liệu liên quan`.
- **Kết quả thực tế:** `Tín hiệu hoàn thành: Tìm thấy 2 tài liệu liên quan`. Smoke test QA trên 10 câu của `test_set.json`: 10/10 hit, 8 câu một-bài F1 = 1.00, 2 câu multi_hop F1 = 0.73.
- **Artifact/log:** `data/chroma/chroma.sqlite3`, `data/embeddings/papers_embeddings*.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Mỗi lần pipeline chạy lại (hoặc chuyển từ corrupted sang repaired), index phải phản ánh đúng bảng dữ liệu hiện tại.
- **Các phương án đã cân nhắc:**
  1. **Upsert** vào collection có sẵn (chỉ ghi đè id trùng).
  2. **Xóa và tạo lại** collection mỗi lần build.
  3. **Một collection chung** cho cả 3 trạng thái, phân biệt bằng metadata `state` và lọc khi query.
- **Phương án đã chọn:** (2), kết hợp mỗi trạng thái một collection riêng.
- **Lý do:**
  - Upsert không xóa vector của tài liệu đã biến mất. `record_id` gồm cả vị trí dòng, nên khi bảng đổi số dòng (24 → 22 → 24), vector cũ sẽ ở lại và vẫn được trả về. Kết quả repaired sẽ bị lẫn dữ liệu bẩn mà không ai biết.
  - Một collection chung buộc mọi query phải lọc đúng `state`. Chỉ cần quên lọc một lần là so sánh sai, và HNSW vẫn phải duyệt cả vector của trạng thái khác.
  - Trade-off: rebuild tốn thời gian embed lại toàn bộ. Với 24 tài liệu, bước index mất vài giây nên chấp nhận được.
- **Bằng chứng quyết định phù hợp:** manifest của 3 collection có đúng 24 / 22 / 24 tài liệu. Hit rate repaired quay về 1.00, không bị kéo xuống bởi vector corrupted.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Lệnh CP2 của hướng dẫn lỗi với code gốc. Tái hiện trên `index.py` ở commit HEAD:
  - `TypeError: LocalEmbeddingIndex.__init__() missing 2 required positional arguments: 'documents' and 'persist_path'`
  - Truyền đủ tham số cho một collection chưa có: `NotFoundError: Collection [papers-does-not-exist] does not exist`
  - Class gốc không có `build_from_clean` và `semantic_search`.
- **Lệnh hoặc bước tái hiện:** Chạy lệnh ở mục 4 với `git show HEAD:src/retrieval/index.py`.
- **Nguyên nhân gốc:** Class gốc được thiết kế chỉ để tạo qua `build()` (tạo collection trước, rồi gọi `__init__` với danh sách tài liệu) hoặc `load()` (đọc manifest). `__init__` gọi `client.get_collection()`, hàm này ném lỗi khi collection chưa tồn tại. Hướng dẫn CP2 lại dùng một API khác (tạo index rỗng rồi build).
- **Cách xử lý:**
  - `__init__`: `collection_name`, `documents`, `persist_path` thành tham số tùy chọn có mặc định; `get_collection` → `get_or_create_collection` (cosine).
  - Chuyển logic build vào method `build_from_clean()`; `build()` chỉ còn tạo instance rồi gọi method này.
  - Thêm `semantic_search()` làm tên gọi khác của `search()`.
- **Cách xác minh sau khi sửa:** Lệnh CP2 in `Tìm thấy 2 tài liệu liên quan`. `run_phase1.py` và `run_corruption_flow.py` (dùng `build()`/`load()`) đều chạy EXIT=0 mà không phải sửa code gọi.
- **Điều học được:** Khi hai bên dùng cùng một class theo hai kiểu khác nhau, nên mở rộng API theo hướng tương thích (tham số tùy chọn, tên gọi khác) thay vì đổi chữ ký cũ, để không làm hỏng các module đang phụ thuộc.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. **Crossref → vector index:** Data Foundation lấy dữ liệu, giữ raw, làm sạch và ghép `text_for_embedding`. Quality gate PASS thì phần của tôi bắt đầu: MiniLM mã hóa mỗi `text_for_embedding` thành vector 384 chiều đã chuẩn hóa, ghi vào collection Chroma dùng khoảng cách cosine, kèm metadata để QA trích câu trả lời mà không phải parse lại văn bản.
2. **Evaluation set:** `retrieval_hit` = có ít nhất một `ground_truth_doc_ids` nằm trong `retrieved_doc_ids` (top-4 của `answer_question`). Chỉ số này đo riêng phần của tôi. Token F1 và judge đo câu trả lời trích từ tài liệu đứng đầu. Nhờ tách hai lớp, `eval_010` corrupted vẫn hit (retrieval ổn) nhưng F1 tụt 0.73 → 0.40: lỗi nằm ở *nội dung* summary bị chèn rác, không nằm ở retrieval.
3. **Quality vs freshness:** quality check (GX) chặn dữ liệu hỏng về cấu trúc (trùng, rỗng, quá ngắn) trước khi vào index. Freshness đo tỉ lệ bài quá 180 ngày. Retrieval ngữ nghĩa không nhìn ngày, nên freshness là tín hiệu duy nhất cho biết index đang phục vụ dữ liệu cũ.
4. **Cùng test set:** để khác biệt về hit rate chỉ đến từ nội dung index. Ba collection tách biệt cộng một test set cố định là một thí nghiệm có đối chứng.
5. **Repair thành công:** collection `papers-repaired` có 24 tài liệu như baseline, `repaired_metrics.json` có hit rate 1.00 và token F1 0.95 bằng baseline, gate PASS và `is_fresh=true`.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal          | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ---------------------- | -------: | --------: | -------: | ------------------------- |
| `retrieval_hit_rate` |     1.00 |      0.70 |     1.00 | Theo loại câu: summary 1.00 → 0.00, authors 1.00 → 0.50; date/categories/multi_hop giữ 1.00 |
| `mean_token_f1`      |     0.95 |      0.84 |     0.95 | Summary 1.00 → 0.65, multi_hop 0.73 → 0.57 |
| `judge_accuracy`     |     1.00 |      0.70 |     0.90 | Không phản ánh retrieval: số câu judge dùng heuristic là 7/10, 0/10, 4/10 |
| `mean_judge_score`   |     4.60 |      3.90 |     4.60 | Như trên |
| Quality checks         | PASS | FAIL (2/6) | PASS | Gate FAIL thì ở production collection corrupted đã không được tạo |
| Freshness status       | FRESH | STALE | FRESH | Retrieval không phát hiện được, vì không dùng ngày |

### Kết luận từ số liệu

1. Bỏ 5 bài mới nhất và cắt tiêu đề → gate FAIL, freshness STALE → collection corrupted chỉ còn 22 tài liệu, hit rate 1.00 → 0.70 (summary 0.00).
2. Rebuild `papers-repaired` từ bảng dựng lại từ raw → gate PASS, FRESH → hit rate 1.00, token F1 0.95, bằng baseline.

**Corruption nào ảnh hưởng rõ nhất và vì sao?**

Với retrieval, `drop_latest_records` là lỗi duy nhất gây miss: 3/3 câu mất hit có ground truth nằm trong 5 bài bị bỏ. Không có vector thì không tìm được. `truncate_title` nguy hiểm theo kiểu khác: tiêu đề bị cắt còn 7 ký tự làm tra cứu chính xác trong `qa.py` thất bại, nên QA phải dựa hoàn toàn vào semantic search. Trong lần chạy này, semantic search vẫn cứu được (`eval_010` vẫn hit nhờ bài thứ nhất).

**Kết quả nào khác với kỳ vọng ban đầu?**

- Tôi kỳ vọng ký tự rác trong `text_for_embedding` làm lệch vector đủ để gây miss. Thực tế 3 bài bị chèn rác (`eval_006`, `eval_008`, `eval_010`) vẫn hit. MiniLM vẫn giữ được nghĩa khi khoảng 2/3 token còn là chữ thật; thiệt hại chỉ hiện ở câu trả lời (F1 0.40).
- Khi kiểm tra thư mục `data/chroma`, tôi thấy **9 thư mục segment nhưng chỉ 3 collection**, tức 6 thư mục mồ côi. Tôi đối chiếu với bảng `segments` trong `chroma.sqlite3`: 3 thư mục đang dùng, 6 không còn được tham chiếu. Giả thuyết: mỗi lần `delete_collection` + `create_collection`, Chroma xóa bản ghi trong SQLite nhưng không xóa thư mục HNSW trên đĩa (trên Windows có thể do file đang bị giữ). Kết quả truy vấn không bị ảnh hưởng, nhưng dung lượng tăng theo số lần chạy.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Data pipeline:** Index là dữ liệu dẫn xuất, nên phải dựng lại được hoàn toàn từ bảng clean. Xóa và tạo lại đơn giản và an toàn hơn cập nhật từng phần.
2. **Data quality/observability:** Retrieval ngữ nghĩa khá "bền" với nhiễu (rác, trùng lặp vẫn hit), nên metric retrieval không đủ để phát hiện dữ liệu bẩn. Quality gate phải đứng *trước* index.
3. **Ảnh hưởng của data đến RAG agent:** Mất tài liệu thì retrieval sai. Tài liệu bẩn thì retrieval vẫn đúng nhưng câu trả lời sai. Hai kiểu hỏng cần hai loại metric khác nhau để thấy.

### Nếu có thêm thời gian

Dọn thư mục segment mồ côi sau mỗi lần rebuild: so danh sách thư mục trong `data/chroma` với bảng `segments` và xóa thư mục không còn được tham chiếu. Lý do: hiện có 6/9 thư mục mồ côi và con số này tăng mỗi lần chạy; repo nộp bài cũng đang chứa chúng. Cách đo: sau hai lần chạy liên tiếp `run_phase1.py` + `run_corruption_flow.py`, số thư mục segment phải đúng bằng 3 và hit rate không đổi.

## 10. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [ ] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [ ] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [ ] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [ ] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [ ] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [ ] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** [Họ và tên]
**Ngày xác nhận:** [YYYY-MM-DD]
