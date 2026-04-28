"""Slice test: integration test for _process_single_chunk.

Mocks only external I/O (GraphDB SPARQL endpoint and section extractor HTTP call)
but runs the real _process_single_chunk logic.
"""
import pytest
import respx
from unittest.mock import patch, MagicMock, call


SECTION_EXTRACTOR_URL = "http://section-extractor:8003"


@pytest.fixture
def mock_graphdb(monkeypatch):
    """Mock all graphdb_writer functions to capture calls."""
    mock_insert_chunk = MagicMock()
    mock_insert_or_merge_section = MagicMock()

    monkeypatch.setattr("app.infrastructure.graphdb_writer.insert_chunk", mock_insert_chunk)
    monkeypatch.setattr("app.infrastructure.graphdb_writer.insert_or_merge_section", mock_insert_or_merge_section)

    return {
        "insert_chunk": mock_insert_chunk,
        "insert_or_merge_section": mock_insert_or_merge_section,
    }


@respx.mock
@pytest.mark.asyncio
async def test_process_chunk_writes_chunk_and_sections(mock_graphdb):
    """Chunk is written to GraphDB and sections are extracted and merged."""
    from app.services.document_service import _process_single_chunk
    import httpx

    # Mock section extractor response
    respx.post(f"{SECTION_EXTRACTOR_URL}/extract-sections").respond(json={
        "sections": [
            {
                "section_id": "introduction",
                "label": "1.1 Introduction",
                "section_enumeration": "1.1",
                "section_type": "Text",
                "confidence": 0.95,
            },
            {
                "section_id": "overview",
                "label": "1.2 Overview",
                "section_enumeration": "1.2",
                "section_type": "Text",
                "confidence": 0.88,
            },
        ]
    })

    element = {
        "text": "1.1 Introduction\nThis is the intro text.",
        "metadata": {"page_number": 1},
    }

    async with httpx.AsyncClient() as client:
        await _process_single_chunk(client, 0, element, "doc-abc")

    # Assert insert_chunk was called with correct args
    mock_graphdb["insert_chunk"].assert_called_once_with(
        "doc-abc_chunk_0", "doc-abc", "1.1 Introduction\nThis is the intro text.", 0, 1
    )

    # Assert insert_or_merge_section was called once per section
    assert mock_graphdb["insert_or_merge_section"].call_count == 2
    calls = mock_graphdb["insert_or_merge_section"].call_args_list
    assert calls[0] == call(
        {"section_id": "introduction", "label": "1.1 Introduction", "section_enumeration": "1.1", "section_type": "Text", "confidence": 0.95},
        "doc-abc_chunk_0",
    )
    assert calls[1] == call(
        {"section_id": "overview", "label": "1.2 Overview", "section_enumeration": "1.2", "section_type": "Text", "confidence": 0.88},
        "doc-abc_chunk_0",
    )


@respx.mock
@pytest.mark.asyncio
async def test_process_chunk_survives_section_extractor_500(mock_graphdb):
    """If section extractor returns 500, chunk is still written and no exception raised."""
    from app.services.document_service import _process_single_chunk
    import httpx

    respx.post(f"{SECTION_EXTRACTOR_URL}/extract-sections").respond(status_code=500)

    element = {
        "text": "Some body text without a clear section.",
        "metadata": {"page_number": 2},
    }

    async with httpx.AsyncClient() as client:
        await _process_single_chunk(client, 1, element, "doc-xyz")

    # Chunk should still be written
    mock_graphdb["insert_chunk"].assert_called_once_with(
        "doc-xyz_chunk_1", "doc-xyz", "Some body text without a clear section.", 1, 2
    )

    # No sections should have been merged
    mock_graphdb["insert_or_merge_section"].assert_not_called()


@respx.mock
@pytest.mark.asyncio
async def test_process_chunk_with_no_page_number(mock_graphdb):
    """Chunks without page_number pass None for page_number."""
    from app.services.document_service import _process_single_chunk
    import httpx

    respx.post(f"{SECTION_EXTRACTOR_URL}/extract-sections").respond(json={"sections": []})

    element = {
        "text": "Plain text without metadata.",
        "metadata": {},
    }

    async with httpx.AsyncClient() as client:
        await _process_single_chunk(client, 5, element, "doc-123")

    mock_graphdb["insert_chunk"].assert_called_once_with(
        "doc-123_chunk_5", "doc-123", "Plain text without metadata.", 5, None
    )