import numpy as np

import embeddings as emb


def test_chunk_text_empty():
    assert emb.chunk_text("") == []
    assert emb.chunk_text(None) == []


def test_chunk_text_small_is_one_chunk():
    assert emb.chunk_text("para one\n\npara two") == ["para one\npara two"]


def test_chunk_text_respects_size_and_overlap():
    paras = [f"paragraph {i} " + "word " * 30 for i in range(30)]
    chunks = emb.chunk_text("\n\n".join(paras), size=400, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 400 + 50 + 1 for c in chunks)
    # consecutive chunks share overlapping text
    assert chunks[0][-20:] in chunks[1]


def test_chunk_text_hard_splits_long_paragraph():
    chunks = emb.chunk_text("x" * 2500, size=1000, overlap=100)
    assert len(chunks) >= 3
    assert all(len(c) <= 1000 for c in chunks)


def test_chunk_text_caps_chunk_count():
    text = "\n\n".join("y" * 900 for _ in range(200))
    assert len(emb.chunk_text(text)) == emb.MAX_CHUNKS


def test_rrf_fuse_rewards_agreement():
    fused, src = emb.rrf_fuse({"semantic": [(1, .9), (2, .8)], "keyword": [(2, 5.0), (3, 4.0)]})
    assert max(fused, key=fused.get) == 2
    assert src[2] == {"semantic", "keyword"}
    assert src[1] == {"semantic"} and src[3] == {"keyword"}
    assert abs(fused[1] - 1 / (emb.RRF_K + 1)) < 1e-12


def test_rrf_fuse_empty():
    assert emb.rrf_fuse({"semantic": [], "keyword": []}) == ({}, {})


def test_normalize_and_blob_roundtrip():
    m = emb._normalize(np.array([[3.0, 4.0], [0.0, 0.0]]))
    assert np.allclose(m[0], [0.6, 0.8])
    assert np.allclose(m[1], [0.0, 0.0])  # zero vector: no divide-by-zero
    assert np.allclose(emb.from_blob(emb.to_blob(m[0])), m[0])


def test_nomic_prefix(monkeypatch):
    monkeypatch.setattr(emb, "EMBED_MODEL", "nomic-embed-text")
    assert emb._prefix(["q"], "query") == ["search_query: q"]
    monkeypatch.setattr(emb, "EMBED_MODEL", "other")
    assert emb._prefix(["q"], "query") == ["q"]


def test_search_degrades_to_keyword_when_ollama_down(temp_db, monkeypatch):
    def down(*a, **k):
        raise emb.EmbeddingError("ollama down")

    monkeypatch.setattr(emb, "embed", down)
    temp_db.create_item(title="Rust ownership", raw_text="borrow checker lifetimes", content_type="note")
    hits, info = emb.search("borrow", mode="hybrid")
    assert info["semantic"] is False
    assert info["keyword"] is True
    assert "ollama down" in info["error"]
    assert isinstance(hits, list)
