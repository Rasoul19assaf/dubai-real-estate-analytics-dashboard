"""Retrieval for the assistant (the R in RAG).

The knowledge base is small and written by the pipeline itself: KPI definitions, the latest
data-quality findings and the documented limitations (assistant/tools.build_corpus).

Two retrievers behind one interface:
  * vector  - documents embedded with a Gemini embedding model, held in LangChain's
              InMemoryVectorStore, searched by cosine similarity
  * keyword - BM25, no network needed
The vector retriever is used when an API key works; if embedding fails for any reason
(quota, model renamed, network) the assistant silently falls back to keyword search, so a
retrieval problem can never take the assistant, or the dashboard, down.
"""
from __future__ import annotations

from assistant.tools import BM25, Doc, build_corpus

DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"


class Retriever:
    def __init__(self, docs: list[Doc] | None = None, embeddings=None):
        self.docs = docs if docs is not None else build_corpus()
        self.bm25 = BM25(self.docs)
        self.store = None
        self.mode = "keyword (BM25)"
        if embeddings is not None:
            try:
                from langchain_core.documents import Document
                from langchain_core.vectorstores import InMemoryVectorStore

                store = InMemoryVectorStore(embeddings)
                store.add_documents([Document(page_content=f"{d.title}. {d.text}", metadata={"i": i})
                                     for i, d in enumerate(self.docs)])
                self.store, self.mode = store, "vector (embeddings)"
            except Exception:  # noqa: BLE001 - any failure -> keyword fallback
                self.store = None

    def search(self, query: str, k: int = 4) -> list[Doc]:
        if self.store is not None:
            try:
                hits = self.store.similarity_search(query, k=k)
                return [self.docs[h.metadata["i"]] for h in hits]
            except Exception:  # noqa: BLE001
                self.store, self.mode = None, "keyword (BM25)"
        return self.bm25.search(query, k=k)


def gemini_embeddings(api_key: str, model: str = DEFAULT_EMBEDDING_MODEL):
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    name = model if model.startswith("models/") else f"models/{model}"
    return GoogleGenerativeAIEmbeddings(model=name, google_api_key=api_key)
