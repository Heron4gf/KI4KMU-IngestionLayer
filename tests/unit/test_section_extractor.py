"""Unit tests for section_extractor/server.py — mock the OpenAI client."""
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Fixture: importable app with mocked OpenAI
# ---------------------------------------------------------------------------

@pytest.fixture
def app_client():
    """Create a FastAPI TestClient with mocked OpenAI client."""
    import sys
    import os

    # Ensure section_extractor is importable
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "section_extractor"))

    # Set required env vars before import
    os.environ.setdefault("LANGEXTRACT_API_KEY", "test-key")
    os.environ.setdefault("LANGEXTRACT_MODEL_ID", "test-model")
    os.environ.setdefault("LANGEXTRACT_PROMPT_PATH", "/dev/null")

    # Import server module first
    import server
    
    # Mock _load_system_prompt to avoid file read, then patch the module-level client
    with patch("server._load_system_prompt", return_value="Test system prompt"):
        with patch.object(server, "client", new=MagicMock()) as mock_client:
            from fastapi.testclient import TestClient
            from server import app
            yield TestClient(app), mock_client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExtractSections:
    def test_valid_response(self, app_client):
        client, mock_openai = app_client

        # Mock the structured output parse() path
        from models import SectionExtractionResponse, SectionExtraction
        mock_parsed = SectionExtractionResponse(
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

        mock_message = MagicMock()
        mock_message.parsed = mock_parsed
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_openai.beta.chat.completions.parse.return_value = mock_response

        resp = client.post("/extract-sections", json={"text": "1.1 Introduction\nSome content here."})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sections"]) == 1
        assert data["sections"][0]["section_id"] == "introduction"
        assert data["sections"][0]["section_enumeration"] == "1.1"

    def test_invalid_llm_data_returns_empty(self, app_client):
        """If the LLM returns structurally invalid data, endpoint returns
        {"sections": []} and does not raise 500."""
        client, mock_openai = app_client

        # parse() returns None
        mock_message = MagicMock()
        mock_message.parsed = None
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_openai.beta.chat.completions.parse.return_value = mock_response

        # Also make the fallback json_object path fail
        mock_openai.chat.completions.create.side_effect = Exception("bad data")

        resp = client.post("/extract-sections", json={"text": "Some random text"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["sections"] == []

    def test_empty_text_returns_empty(self, app_client):
        client, mock_openai = app_client

        resp = client.post("/extract-sections", json={"text": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert data["sections"] == []
        # OpenAI should not have been called
        mock_openai.beta.chat.completions.parse.assert_not_called()

    def test_health_endpoint(self, app_client):
        client, _ = app_client

        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}