import time
import threading
from pathlib import Path

import requests
import streamlit as st

API_BASE = "http://localhost:8000/v1"

SSTATUS_ICON = {
    "pending": "⏳",
    "processing": "🔄",
    "completed": "✅",
    "failed": "❌",
}


def submit_document(file_bytes: bytes, filename: str) -> dict | None:
    try:
        response = requests.post(
            f"{API_BASE}/documents",
            files={"file": (filename, file_bytes, "application/pdf")},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        st.error(f"Failed to submit {filename}: {e}")
        return None


def fetch_job_status(job_id: str) -> dict | None:
    try:
        response = requests.get(f"{API_BASE}/jobs/{job_id}", timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None


def is_terminal(status: str) -> bool:
    return status in ("completed", "failed")


st.set_page_config(page_title="Document Ingestion", page_icon="📄", layout="centered")
st.title("📄 Document Ingestion")
st.caption("Upload PDF documents to ingest them into the knowledge base.")

if "jobs" not in st.session_state:
    st.session_state.jobs = {}  # job_id -> {filename, status, ...}

with st.form("upload_form", clear_on_submit=True):
    uploaded_files = st.file_uploader(
        "Select PDF files",
        type=["pdf"],
        accept_multiple_files=True,
    )
    submitted = st.form_submit_button("🚀 Start Ingestion")

if submitted and uploaded_files:
    for uploaded_file in uploaded_files:
        file_bytes = uploaded_file.read()
        result = submit_document(file_bytes, uploaded_file.name)
        if result:
            job_id = result["job_id"]
            st.session_state.jobs[job_id] = {
                "filename": uploaded_file.name,
                "status": result.get("status", "pending"),
                "document_id": None,
                "num_chunks": None,
                "error": None,
            }
elif submitted and not uploaded_files:
    st.warning("Please select at least one PDF file before submitting.")

if st.session_state.jobs:
    st.divider()
    st.subheader("Ingestion Jobs")

    all_done = all(
        is_terminal(job["status"]) for job in st.session_state.jobs.values()
    )

    for job_id, job in st.session_state.jobs.items():
        icon = SSTATUS_ICON.get(job["status"], "❓")
        col1, col2, col3 = st.columns([4, 2, 2])
        col1.write(f"**{job['filename']}**")
        col2.write(f"{icon} `{job['status']}`")

        if job["status"] == "completed":
            col3.write(f"🧩 {job['num_chunks']} chunks")
        elif job["status"] == "failed":
            col3.write(f"⚠️ {job['error'] or 'Unknown error'}")
        else:
            col3.write("")

    if not all_done:
        for job_id, job in st.session_state.jobs.items():
            if not is_terminal(job["status"]):
                updated = fetch_job_status(job_id)
                if updated:
                    job["status"] = updated.get("status", job["status"])
                    job["document_id"] = updated.get("document_id")
                    job["num_chunks"] = updated.get("num_chunks")
                    job["error"] = updated.get("error")
        time.sleep(1)
        st.rerun()
