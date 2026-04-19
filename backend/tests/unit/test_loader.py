"""Unit tests for the document loader."""

from __future__ import annotations

import pytest

from app.services.ingestion.loader import load_text, DocumentDraft


class TestLoadText:
    def test_basic_load(self):
        draft = load_text(title="Test Doc", text="Hello, world!")
        assert isinstance(draft, DocumentDraft)
        assert draft.title == "Test Doc"
        assert "Hello" in draft.text

    def test_content_hash_is_stable(self):
        draft1 = load_text(title="Doc", text="Same content")
        draft2 = load_text(title="Doc", text="Same content")
        assert draft1.content_hash == draft2.content_hash

    def test_different_content_different_hash(self):
        draft1 = load_text(title="Doc", text="Content A")
        draft2 = load_text(title="Doc", text="Content B")
        assert draft1.content_hash != draft2.content_hash

    def test_source_type_text(self):
        draft = load_text(title="Doc", text="Some text")
        assert draft.source_type == "text"

    def test_source_uri_is_none_for_inline_text(self):
        # By design: source_uri is only set when loading from a URL, not inline text.
        draft = load_text(title="My Document", text="content")
        assert draft.source_uri is None

    def test_html_not_stripped_for_inline_text(self):
        # HTML stripping only happens for URL fetches with text/html content-type.
        # Inline text is stored as-is.
        html = "<h1>Title</h1><p>Some <b>bold</b> content.</p>"
        draft = load_text(title="HTML Doc", text=html)
        # The raw text should be preserved unchanged
        assert draft.text == html

    def test_extra_meta_passed_through(self):
        draft = load_text(title="Doc", text="text", meta={"source": "wikipedia"})
        assert draft.meta.get("source") == "wikipedia"

    def test_empty_text_raises_or_loads(self):
        # Should not crash; empty content is a valid (if unusual) input
        try:
            draft = load_text(title="Empty", text="")
            assert draft.content_hash  # still has a hash
        except ValueError:
            pass  # acceptable to reject empty text
