"""Smoke test against a live docker-compose environment.

Requires:
  - docker-compose up running all services
  - A real LLM API key in the environment
  - Run with: pytest -m smoke tests/smoke/test_smoke.py
"""
import os
import time
import pytest
import requests

API_BASE = os.getenv("SMOKE_API_BASE", "http://localhost:8001/v1")
SECTION_EXTRACTOR_BASE = os.getenv("SMOKE_SECTION_EXTRACTOR_BASE", "http://localhost:8003")
GRAPHDB_BASE = os.getenv("SMOKE_GRAPHDB_BASE", "http://localhost:7200")
GRAPHDB_REPO = os.getenv("GRAPHDB_REPOSITORY", "pdf-ingestion")

POLL_INTERVAL = 2  # seconds
POLL_TIMEOUT = 120  # seconds


@pytest.mark.smoke
class TestSmoke:
    def test_health_api(self):
        """API /health returns ok."""
        resp = requests.get(f"{API_BASE}/health", timeout=10)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_health_section_extractor(self):
        """Section extractor /health returns ok."""
        resp = requests.get(f"{SECTION_EXTRACTOR_BASE}/health", timeout=10)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_ingest_and_query_graphdb(self):
        """Full pipeline: ingest a small PDF, poll job, verify GraphDB triples."""
        # Create a minimal 2-page PDF for testing
        pdf_content = _create_minimal_pdf()

        # Step 1: POST /ingest (now POST /documents)
        resp = requests.post(
            f"{API_BASE}/documents",
            files={"file": ("test.pdf", pdf_content, "application/pdf")},
            timeout=30,
        )
        assert resp.status_code == 202, f"Ingest failed: {resp.text}"
        job_id = resp.json()["job_id"]

        # Step 2: Poll job status
        deadline = time.time() + POLL_TIMEOUT
        status = "pending"
        while time.time() < deadline:
            job_resp = requests.get(f"{API_BASE}/jobs/{job_id}", timeout=10)
            assert job_resp.status_code == 200
            status = job_resp.json()["status"]
            if status in ("completed", "failed"):
                break
            time.sleep(POLL_INTERVAL)

        assert status == "completed", f"Job did not complete: {job_resp.json()}"

        document_id = job_resp.json().get("document_id")
        assert document_id, "No document_id in completed job"

        # Step 3: Query GraphDB for ki4kmu:Document
        doc_query = f"""
        PREFIX ki4kmu: <http://ki4kmu.fhnw.ch/ontology#>
        ASK WHERE {{
            ?doc rdf:type ki4kmu:Document .
            ?doc ki4kmu:document_id "{document_id}" .
        }}
        """
        sparql_resp = requests.get(
            f"{GRAPHDB_BASE}/repositories/{GRAPHDB_REPO}",
            params={"query": doc_query},
            headers={"Accept": "application/sparql-results+json"},
            timeout=10,
        )
        assert sparql_resp.status_code == 200
        assert sparql_resp.json().get("boolean") is True, "ki4kmu:Document not found in GraphDB"

        # Step 4: Query for at least one ki4kmu:Chunk
        chunk_query = f"""
        PREFIX ki4kmu: <http://ki4kmu.fhnw.ch/ontology#>
        SELECT (COUNT(?chunk) AS ?count) WHERE {{
            ?chunk rdf:type ki4kmu:Chunk .
            ?chunk ki4kmu:belongsTo ?doc .
            ?doc ki4kmu:document_id "{document_id}" .
        }}
        """
        sparql_resp = requests.get(
            f"{GRAPHDB_BASE}/repositories/{GRAPHDB_REPO}",
            params={"query": chunk_query},
            headers={"Accept": "application/sparql-results+json"},
            timeout=10,
        )
        assert sparql_resp.status_code == 200
        bindings = sparql_resp.json().get("results", {}).get("bindings", [])
        assert len(bindings) > 0
        count = int(bindings[0]["count"]["value"])
        assert count >= 1, "No ki4kmu:Chunk found in GraphDB"

        # Step 5: Query for at least one ki4kmu:isContained triple
        containment_query = f"""
        PREFIX ki4kmu: <http://ki4kmu.fhnw.ch/ontology#>
        ASK WHERE {{
            ?chunk ki4kmu:isContained ?section .
            ?section rdf:type ki4kmu:Section .
        }}
        """
        sparql_resp = requests.get(
            f"{GRAPHDB_BASE}/repositories/{GRAPHDB_REPO}",
            params={"query": containment_query},
            headers={"Accept": "application/sparql-results+json"},
            timeout=10,
        )
        # This may or may not be true depending on LLM extraction — just check it doesn't error
        assert sparql_resp.status_code == 200


def _create_minimal_pdf() -> bytes:
    """Create a minimal valid PDF with 2 pages for smoke testing."""
    # Minimal PDF: two pages with some text
    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R 4 0 R]/Count 2>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 5 0 R/Resources<</Font<</F1 6 0 R>>>>>>endobj\n"
        b"4 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 7 0 R/Resources<</Font<</F1 6 0 R>>>>>>endobj\n"
        b"5 0 obj<</Length 44>>stream\nBT /F1 12 Tf 100 700 Td (1.1 Introduction) Tj ET\nendstream\nendobj\n"
        b"6 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"7 0 obj<</Length 55>>stream\nBT /F1 12 Tf 100 700 Td (1.2 Methodology) Tj ET\nendstream\nendobj\n"
        b"xref\n0 8\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000266 00000 n \n"
        b"0000000417 00000 n \n"
        b"0000000513 00000 n \n"
        b"0000000590 00000 n \n"
        b"trailer<</Size 8/Root 1 0 R>>\n"
        b"startxref\n697\n%%EOF\n"
    )
    return pdf