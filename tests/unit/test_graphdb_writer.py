"""Unit tests for app.infrastructure.graphdb_writer — new ki4kmu: ontology."""
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Patch SPARQLWrapper so the module can be imported without a live GraphDB
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_sparql(monkeypatch):
    """Prevent any real SPARQL calls during import or execution."""
    mock_client = MagicMock()
    monkeypatch.setattr(
        "app.infrastructure.graphdb_writer._get_write_client",
        lambda: mock_client,
    )
    return mock_client


# ---------------------------------------------------------------------------
# insert_document
# ---------------------------------------------------------------------------

class TestInsertDocument:
    def test_emits_document_type_and_id(self, _mock_sparql):
        from app.infrastructure.graphdb_writer import insert_document

        insert_document("doc-abc", "deadbeef123")

        call_args = _mock_sparql.setQuery.call_args[0][0]
        assert "ki4kmu:Document" in call_args
        assert "doc-abc" in call_args
        assert "deadbeef123" in call_args
        assert "ki4kmu:document_id" in call_args
        assert "ki4kmu:pdf_hash" in call_args


# ---------------------------------------------------------------------------
# insert_chunk
# ---------------------------------------------------------------------------

class TestInsertChunk:
    def test_emits_chunk_type_and_belongsTo(self, _mock_sparql):
        from app.infrastructure.graphdb_writer import insert_chunk

        insert_chunk("doc1_chunk_0", "doc1", "Hello world", 0, page_number=3)

        call_args = _mock_sparql.setQuery.call_args[0][0]
        assert "ki4kmu:Chunk" in call_args
        assert "ki4kmu:belongsTo" in call_args
        assert "ki4kmu:chunk_index" in call_args
        assert "ki4kmu:text" in call_args
        assert "Hello world" in call_args
        assert "ki4kmu:page_number" in call_args

    def test_omits_page_when_none(self, _mock_sparql):
        from app.infrastructure.graphdb_writer import insert_chunk

        insert_chunk("doc1_chunk_0", "doc1", "Text", 0)

        call_args = _mock_sparql.setQuery.call_args[0][0]
        assert "ki4kmu:page_number" not in call_args

    def test_document_uri_in_triples(self, _mock_sparql):
        from app.infrastructure.graphdb_writer import insert_chunk

        insert_chunk("doc1_chunk_0", "doc1", "Text", 0)

        call_args = _mock_sparql.setQuery.call_args[0][0]
        assert "doc_doc1" in call_args
        # Both chunk and document URIs should use angle-bracket full IRIs
        assert "<http://ki4kmu.fhnw.ch/ontology#" in call_args


# ---------------------------------------------------------------------------
# insert_image
# ---------------------------------------------------------------------------

class TestInsertImage:
    def test_emits_image_type_and_base64(self, _mock_sparql):
        from app.infrastructure.graphdb_writer import insert_image

        insert_image("doc1_image_0", "doc1", "base64data==", page_number=5)

        call_args = _mock_sparql.setQuery.call_args[0][0]
        assert "ki4kmu:Image" in call_args
        assert "ki4kmu:belongsTo" in call_args
        assert "ki4kmu:image_base64" in call_args
        assert "base64data==" in call_args
        assert "ki4kmu:page_number" in call_args


# ---------------------------------------------------------------------------
# insert_or_merge_section
# ---------------------------------------------------------------------------

class TestInsertOrMergeSection:
    def test_emits_containment_and_section_metadata(self, _mock_sparql):
        from app.infrastructure.graphdb_writer import insert_or_merge_section

        section = {
            "section_id": "introduction",
            "section_enumeration": "1.1",
            "section_type": "Text",
            "confidence": 0.95,
        }
        insert_or_merge_section(section, "doc1_chunk_0")

        # Should have been called twice: containment + section metadata
        assert _mock_sparql.setQuery.call_count == 2

        calls = [c[0][0] for c in _mock_sparql.setQuery.call_args_list]

        # First call: containment edge
        assert "ki4kmu:isContained" in calls[0]

        # Second call: section metadata
        assert "ki4kmu:Section" in calls[1]
        assert "ki4kmu:Text" in calls[1]
        assert "ki4kmu:section_id" in calls[1]
        assert "ki4kmu:section_enumeration" in calls[1]
        assert "introduction" in calls[1]
        assert "1.1" in calls[1]

    def test_image_section_type(self, _mock_sparql):
        from app.infrastructure.graphdb_writer import insert_or_merge_section

        section = {
            "section_id": "figure_1",
            "label": "Figure 1",
            "section_enumeration": "",
            "section_type": "Image",
            "confidence": 0.90,
        }
        insert_or_merge_section(section, "doc1_chunk_0")

        calls = [c[0][0] for c in _mock_sparql.setQuery.call_args_list]
        assert "ki4kmu:Image" in calls[1]

    def test_empty_section_id_is_skipped(self, _mock_sparql):
        from app.infrastructure.graphdb_writer import insert_or_merge_section

        section = {
            "section_id": "",
            "section_enumeration": "",
            "section_type": "Text",
            "confidence": 0.5,
        }
        insert_or_merge_section(section, "doc1_chunk_0")

        assert _mock_sparql.setQuery.call_count == 0

    def test_same_section_called_twice_emits_two_containment_edges(self, _mock_sparql):
        """Two chunks in the same section → two containment triples but section
        metadata written twice (idempotent in RDF)."""
        from app.infrastructure.graphdb_writer import insert_or_merge_section

        section = {
            "section_id": "methods",
            "label": "2 Methods",
            "section_enumeration": "2",
            "section_type": "Text",
            "confidence": 0.95,
        }
        insert_or_merge_section(section, "doc1_chunk_0")
        insert_or_merge_section(section, "doc1_chunk_1")

        assert _mock_sparql.setQuery.call_count == 4  # 2 containment + 2 section metadata

        calls = [c[0][0] for c in _mock_sparql.setQuery.call_args_list]
        containment_calls = [c for c in calls if "ki4kmu:isContained" in c]
        assert len(containment_calls) == 2
        assert "doc1_chunk_0" in containment_calls[0]
        assert "doc1_chunk_1" in containment_calls[1]