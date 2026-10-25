from pathlib import Path

from langchain_core.embeddings import Embeddings

from claude_code.config import config
from claude_code.context.indexers import semantic_indexer


class FakeEmbeddings(Embeddings):
    def __init__(self) -> None:
        self.document_batches: list[list[str]] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_batches.append(texts)
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> list[float]:
        return [float(len(text)), float(sum(map(ord, text)) % 101), 1.0]


def test_faiss_indexer_only_embeds_changed_files(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text("def first():\n    return 1\n", encoding="utf-8")
    monkeypatch.setitem(
        config,
        "faiss",
        {"persist_dir": str(tmp_path / ".faiss"), "index_name": "codebase"},
    )
    embeddings = FakeEmbeddings()
    monkeypatch.setattr(semantic_indexer, "get_embedder", lambda: embeddings)

    first_index = semantic_indexer.index_codebase(str(tmp_path))
    first_batch_count = len(embeddings.document_batches)
    unchanged_index = semantic_indexer.index_codebase(str(tmp_path))

    assert first_index.index.ntotal == 1
    assert unchanged_index.index.ntotal == 1
    assert len(embeddings.document_batches) == first_batch_count

    source.write_text(
        "def first():\n    return 1\n\ndef second():\n    return 2\n",
        encoding="utf-8",
    )
    changed_index = semantic_indexer.index_codebase(str(tmp_path))

    assert changed_index.index.ntotal == 2
    assert len(embeddings.document_batches) == first_batch_count + 1
