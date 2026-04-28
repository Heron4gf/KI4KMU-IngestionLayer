"""Unit tests for section_extractor/server.py — mock the LangChain chain."""
import pytest
from unittest.mock import patch, MagicMock

from models import SectionExtractionResponse, SectionExtraction


@pytest.fixture
def app_client():
    """Create a FastAPI TestClient with mocked LangChain chain."""
    import sys
    import os

    # Ensure section_extractor is importable
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "section_extractor"))

    # Set required env vars before import
    os.environ.setdefault("EXTRACTOR_API_KEY", "test-key")
    os.environ.setdefault("EXTRACTOR_MODEL_ID", "test-model")
    os.environ.setdefault("EXTRACTOR_PROMPT_PATH", "/dev/null")

    # Mock _load_system_prompt to avoid file read, then patch the module-level chain
    with patch("server._load_system_prompt", return_value="Test system prompt"):
        with patch.object(server, "chain", new=MagicMock()) as mock_chain:
            from fastapi.testclient import TestClient
            from server import app
            yield TestClient(app), mock_chain


class TestExtractSections:
    def test_valid_response(self, app_client):
        client, mock_chain = app_client

        mock_result = SectionExtractionResponse(
            sections=[
                SectionExtraction(
                    section_id="introduction",
                    label="1.1 Introduction",
                    section_enumeration="1.1",
                    section_type="Text",
                    confidence=0.95,
                )
            ]
        )
        mock_chain.invoke.return_value = mock_result

        resp = client.post("/extract-sections", json={"text": "1.1 Introduction\nSome content here."})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sections"]) == 1
        assert data["sections"][0]["section_id"] == "introduction"
        assert data["sections"][0]["section_enumeration"] == "1.1"

    def test_invalid_llm_data_returns_empty(self, app_client):
        """If the LLM returns invalid data, endpoint returns {"sections": []}."""
        client, mock_chain = app_client
        mock_chain.invoke.side_effect = Exception("bad data")

        resp = client.post("/extract-sections", json={"text": "Some random text"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["sections"] == []

    def test_empty_text_returns_empty(self, app_client):
        client, mock_chain = app_client

        resp = client.post("/extract-sections", json={"text": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert data["sections"] == []
        # Chain should not have been called
        mock_chain.invoke.assert_not_called()

    def test_health_endpoint(self, app_client):
        client, _ = app_client

        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
