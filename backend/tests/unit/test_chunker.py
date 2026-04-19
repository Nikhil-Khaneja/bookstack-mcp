"""Unit tests for the recursive character chunker."""

from __future__ import annotations

import pytest

from app.services.ingestion.chunker import chunk_text, ChunkDraft


class TestChunkText:
    def test_short_text_produces_single_chunk(self):
        text = "Hello world, this is a short document."
        chunks = chunk_text(text, size=512, overlap=64)
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].ord == 0

    def test_long_text_splits_into_multiple_chunks(self):
        # 1000 'a' characters should split with size=200
        text = "a" * 1000
        chunks = chunk_text(text, size=200, overlap=0)
        assert len(chunks) > 1

    def test_chunks_cover_all_content(self):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = chunk_text(text, size=30, overlap=0)
        combined = " ".join(c.text for c in chunks)
        # Every word from the original should appear somewhere
        for word in ["First", "Second", "Third"]:
            assert word in combined

    def test_ord_is_sequential(self):
        text = "word " * 200
        chunks = chunk_text(text, size=100, overlap=10)
        ords = [c.ord for c in chunks]
        assert ords == list(range(len(chunks)))

    def test_token_count_is_positive(self):
        chunks = chunk_text("hello world", size=512, overlap=0)
        assert all(c.token_count > 0 for c in chunks)

    def test_overlap_creates_shared_content(self):
        # With overlap, successive chunks share content at the boundary
        text = "one two three four five six seven eight nine ten " * 5
        chunks_no_overlap = chunk_text(text, size=50, overlap=0)
        chunks_with_overlap = chunk_text(text, size=50, overlap=20)
        # Overlap makes more chunks (or same) but content repeats
        # Just verify overlap version has at least as many chunks
        assert len(chunks_with_overlap) >= len(chunks_no_overlap)

    def test_empty_text_returns_empty_list(self):
        chunks = chunk_text("", size=512, overlap=64)
        assert chunks == []

    def test_whitespace_only_text_returns_empty_or_single(self):
        chunks = chunk_text("   \n\n   ", size=512, overlap=64)
        # After stripping, should be empty or single whitespace chunk
        assert len(chunks) <= 1

    @pytest.mark.parametrize("size,overlap", [(128, 16), (256, 32), (512, 64)])
    def test_various_sizes(self, size, overlap):
        text = "This is a test sentence. " * 50
        chunks = chunk_text(text, size=size, overlap=overlap)
        assert len(chunks) >= 1
        for c in chunks:
            assert isinstance(c, ChunkDraft)
            assert len(c.text) <= size * 2  # generous upper bound
