from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
import pandas as pd

from core.config import Settings
from core.utils import read_json, safe_slug, write_json
from retrieval.embeddings import MiniLMEmbeddings


@dataclass(frozen=True)
class SearchResult:
    paper_id: str
    title: str
    score: float
    content: str
    metadata: dict[str, Any]


class LocalEmbeddingIndex:
    def __init__(
        self,
        settings: Settings,
        collection_name: str | None = None,
        documents: list[dict[str, Any]] | None = None,
        persist_path: Path | None = None,
    ):
        self.settings = settings
        self.collection_name = collection_name or settings.baseline_collection_name
        self.persist_path = persist_path or settings.paths.chroma_dir
        self.documents = documents or []
        self.embedding_backend = "chroma"
        self.embedding_model = MiniLMEmbeddings(settings.embedding_model)
        self.persist_path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.persist_path))
        self.documents_by_paper_id = {
            document["paper_id"].lower(): document for document in self.documents if "paper_id" in document
        }
        self.documents_by_title = {
            document["title"].lower(): document for document in self.documents if "title" in document
        }

    @property
    def collection(self):
        try:
            return self.client.get_collection(name=self.collection_name)
        except Exception:
            try:
                return self.client.create_collection(
                    name=self.collection_name,
                    configuration={"hnsw": {"space": "cosine"}},
                )
            except Exception:
                return self.client.get_or_create_collection(name=self.collection_name)

    def build_from_clean(
        self,
        clean_path: Path | str | None = None,
        df: pd.DataFrame | None = None,
        embeddings_output_path: Path | None = None,
    ) -> "LocalEmbeddingIndex":
        """Nạp dữ liệu sạch từ dataframe hoặc file clean JSON/CSV và đánh chỉ mục lên ChromaDB."""
        if df is None:
            path = Path(clean_path or self.settings.paths.clean_json)
            if path.exists():
                df = pd.read_json(path)
            elif self.settings.paths.clean_csv.exists():
                df = pd.read_csv(self.settings.paths.clean_csv)
            else:
                raise FileNotFoundError(f"Clean papers not found at {path} or {self.settings.paths.clean_csv}")

        self.documents = self._build_documents(df)
        self.documents_by_paper_id = {
            doc["paper_id"].lower(): doc for doc in self.documents if "paper_id" in doc
        }
        self.documents_by_title = {
            doc["title"].lower(): doc for doc in self.documents if "title" in doc
        }

        try:
            self.client.delete_collection(name=self.collection_name)
        except Exception:
            pass

        try:
            coll = self.client.create_collection(
                name=self.collection_name,
                configuration={"hnsw": {"space": "cosine"}},
            )
        except Exception:
            coll = self.client.get_or_create_collection(name=self.collection_name)

        embeddings = self.embedding_model.embed_documents([doc["content"] for doc in self.documents])
        coll.add(
            ids=[doc["record_id"] for doc in self.documents],
            embeddings=embeddings,
            documents=[doc["content"] for doc in self.documents],
            metadatas=[doc["metadata"] for doc in self.documents],
        )

        manifest_path = embeddings_output_path or self.settings.paths.embeddings_json
        write_json(
            manifest_path,
            {
                "backend": "chroma",
                "embedding_model": self.settings.embedding_model,
                "persist_path": str(self.persist_path),
                "collection_name": self.collection_name,
                "documents": self.documents,
            },
        )
        return self

    def semantic_search(self, query: str, top_k: int | None = None) -> list[SearchResult]:
        """Alias cho search(), tìm kiếm ngữ nghĩa các tài liệu liên quan nhất."""
        return self.search(query=query, top_k=top_k)

    @staticmethod
    def _build_documents(df: pd.DataFrame) -> list[dict[str, Any]]:
        records = df.to_dict(orient="records")
        documents: list[dict[str, Any]] = []
        for index, row in enumerate(records):
            documents.append(
                {
                    "record_id": f"{row['paper_id']}::{index}",
                    "paper_id": row["paper_id"],
                    "title": row["title"],
                    "content": row["text_for_embedding"],
                    "metadata": {
                        "paper_id": row["paper_id"],
                        "title": row["title"],
                        "published": row["published"],
                        "authors_joined": row["authors_joined"],
                        "categories_joined": row["categories_joined"],
                        "summary": row["summary"],
                        "abs_url": row["abs_url"],
                        "pdf_url": row["pdf_url"],
                    },
                }
            )
        return documents

    @staticmethod
    def _derive_collection_name(settings: Settings, embeddings_output_path: Path | None) -> str:
        if embeddings_output_path is None:
            return settings.baseline_collection_name

        name_map = {
            settings.paths.embeddings_json.resolve(): settings.baseline_collection_name,
            settings.paths.corrupted_embeddings_json.resolve(): settings.corrupted_collection_name,
            settings.paths.repaired_embeddings_json.resolve(): settings.repaired_collection_name,
        }
        resolved_path = embeddings_output_path.resolve()
        if resolved_path in name_map:
            return name_map[resolved_path]
        return safe_slug(embeddings_output_path.stem)

    @classmethod
    def build(
        cls,
        df: pd.DataFrame,
        settings: Settings,
        embeddings_output_path: Path | None = None,
    ) -> "LocalEmbeddingIndex":
        collection_name = cls._derive_collection_name(settings, embeddings_output_path)
        idx = cls(
            settings=settings,
            collection_name=collection_name,
            persist_path=settings.paths.chroma_dir,
        )
        return idx.build_from_clean(df=df, embeddings_output_path=embeddings_output_path)

    @classmethod
    def load(cls, settings: Settings, embeddings_path: Path | None = None) -> "LocalEmbeddingIndex":
        payload = read_json(embeddings_path or settings.paths.embeddings_json)
        return cls(
            settings=settings,
            collection_name=payload["collection_name"],
            documents=payload["documents"],
            persist_path=Path(payload["persist_path"]),
        )

    def search(self, query: str, top_k: int | None = None) -> list[SearchResult]:
        query_embedding = self.embedding_model.embed_query(query)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k or self.settings.top_k,
            include=["documents", "metadatas", "distances"],
        )
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        scored: list[SearchResult] = []
        for record_id, content, metadata, distance in zip(ids, documents, metadatas, distances, strict=False):
            if not record_id or not metadata or not content:
                continue
            scored.append(
                SearchResult(
                    paper_id=str(metadata["paper_id"]),
                    title=str(metadata["title"]),
                    score=max(0.0, 1.0 - float(distance or 0.0)),
                    content=str(content),
                    metadata=dict(metadata),
                )
            )
        return scored

    def lookup(self, value: str) -> dict[str, Any] | None:
        needle = value.strip().lower()
        if needle in self.documents_by_paper_id:
            return self.documents_by_paper_id[needle]
        if needle in self.documents_by_title:
            return self.documents_by_title[needle]
        return None
