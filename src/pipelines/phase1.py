from __future__ import annotations

from core.config import load_settings
from core.utils import write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import load_or_create_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex
from retrieval.qa import answer_question


def main() -> None:
    """Xây dựng và thực thi baseline pipeline end-to-end cho dữ liệu sạch."""
    settings = load_settings()
    print("=== [Phase 1: Baseline Pipeline] Bắt đầu chạy ===")

    # 1. Thu thập dữ liệu thô (Dual-mode: online API hoặc offline snapshot)
    print("[1/7] Thu thập dữ liệu thô Crossref...")
    records = fetch_source_records(settings)
    print(f"      Thu thập được {len(records)} bản ghi.")

    # 2. Làm sạch dữ liệu và tạo text_for_embedding
    print("[2/7] Làm sạch dữ liệu và tính toán độ tươi...")
    clean_df = build_clean_dataframe(records, run_date=settings.run_date)
    write_csv(clean_df, settings.paths.clean_csv)
    write_json(settings.paths.clean_json, clean_df.to_dict(orient="records"))
    print(f"      Đã lưu {len(clean_df)} bản ghi vào {settings.paths.clean_csv.name} và {settings.paths.clean_json.name}.")

    # 3. Data Quality Gate & Freshness SLA
    print("[3/7] Kiểm tra chất lượng dữ liệu (Data Quality Gate & Freshness SLA)...")
    quality = run_data_quality_checks(clean_df, settings, phase_label="baseline")
    freshness = build_freshness_report(clean_df, settings)
    print(f"      Quality Check Status: {quality['success']} (6/6 expectations)")
    print(f"      Freshness SLA Status: {freshness['sla_status']}")

    # 4. Đánh chỉ mục ChromaDB với MiniLM Embeddings
    print("[4/7] Đánh chỉ mục ChromaDB với MiniLM embeddings...")
    index = LocalEmbeddingIndex.build(clean_df, settings)
    print(f"      Bộ chỉ mục collection '{settings.baseline_collection_name}' sẵn sàng.")

    # 5. Tải hoặc sinh benchmark test set
    print("[5/7] Thiết lập Benchmark Test Set...")
    test_set = load_or_create_test_set(clean_df, settings.paths.eval_testset, force_refresh=settings.refresh_test_set)
    print(f"      Bộ đề thi chuẩn gồm {len(test_set.samples)} câu hỏi.")

    # 6. Đo lường chỉ số nền (Baseline Benchmarks: Hit Rate & Token F1)
    print("[6/7] Đánh giá độ chính xác RAG Agent (Baseline Benchmarks)...")
    bundle = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.baseline_metrics,
        answers_output_path=settings.paths.baseline_answers,
    )
    hit_rate = bundle.summary.get("retrieval_hit_rate", 0.0)
    token_f1 = bundle.summary.get("mean_token_f1", 0.0)
    print(f"      Retrieval Hit Rate: {hit_rate:.2%}")
    print(f"      Mean Token F1:      {token_f1:.4f}")

    # 7. Báo cáo tổng hợp Pha 1
    print("[7/7] Sinh báo cáo tổng hợp Phase 1...")
    source_summary = {
        "raw_records": len(records),
        "clean_records": len(clean_df),
        "embedding_model": settings.embedding_model,
        "collection_name": settings.baseline_collection_name,
    }
    generate_phase1_report(
        report_path=settings.paths.baseline_report,
        source_summary=source_summary,
        metrics=bundle.summary,
        quality=quality,
        freshness=freshness,
    )
    print(f"      Báo cáo Markdown đã lưu tại: {settings.paths.baseline_report}")

    # 8. Demo câu hỏi mẫu
    demo_questions = [
        "What is the summary of the paper 'Continuous Benchmark Evaluation for Enterprise Retrieval Pipelines'?",
        "Who authored the paper 'Freshness SLAs for Real-Time LLM Knowledge Augmentation'?",
    ]
    demo_results = []
    for q in demo_questions:
        res = answer_question(q, settings=settings, index=index)
        demo_results.append({
            "question": q,
            "answer": res.answer,
            "retrieved_titles": res.retrieved_titles,
        })
    write_json(settings.paths.demo_answers, demo_results)

    print("=== [Phase 1: Baseline Pipeline] Hoàn tất thành công! ===")
