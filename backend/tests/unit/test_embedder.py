"""Unit tests for the HashingEmbedder offline fallback."""

from __future__ import annotations

import numpy as np
import pytest

from app.services.retrieval.embedder import HashingEmbedder


@pytest.fixture()
def emb():
    return HashingEmbedder(dim=384)


class TestHashingEmbedder:
    def test_output_shape(self, emb):
        vecs = emb.encode(["hello world", "another sentence"])
        assert len(vecs) == 2
        assert len(vecs[0]) == 384

    def test_unit_normalized(self, emb):
        vecs = emb.encode(["test text for normalization"])
        norm = np.linalg.norm(vecs[0])
        assert abs(norm - 1.0) < 1e-5

    def test_deterministic(self, emb):
        text = "Transformers use multi-head attention"
        v1 = emb.encode([text])[0]
        v2 = emb.encode([text])[0]
        assert v1 == v2

    def test_different_texts_produce_different_embeddings(self, emb):
        v1 = emb.encode(["The quick brown fox"])[0]
        v2 = emb.encode(["Vector databases store embeddings"])[0]
        assert v1 != v2

    def test_empty_string_handled(self, emb):
        vecs = emb.encode([""])
        assert len(vecs) == 1
        assert len(vecs[0]) == 384

    def test_batch_encode(self, emb):
        texts = [f"sentence number {i}" for i in range(10)]
        vecs = emb.encode(texts)
        assert len(vecs) == 10
        for v in vecs:
            assert len(v) == 384

    def test_dim_property(self, emb):
        assert emb.dim == 384

    def test_name_property(self, emb):
        assert "hashing" in emb.name.lower()

    @pytest.mark.parametrize("dim", [128, 256, 384, 768])
    def test_custom_dim(self, dim):
        e = HashingEmbedder(dim=dim)
        vecs = e.encode(["test"])
        assert len(vecs[0]) == dim
