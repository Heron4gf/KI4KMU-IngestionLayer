import os
import time
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8001/v1")

SSTATUS_ICON = {
    "pending": "⏳",
    "processing": "🔄",
    "completed": "✅",
    "failed": "❌",
}

STAGE_LABELS = {
    "upload_received": "📥 Upload Received",
    "chunking_text": "✂️ Chunking Text",
    "extracting_images": "🖼️ Extracting Images",
    "storing_chunks": "💾 Storing Chunks",
    "extracting_entities": "🔍 Extracting Entities",
    "writing_graphdb": "🕸️ Writing to GraphDB",
    "completed": "✅ Completed",
    "failed": "❌ Failed",
}

STAGE_PROGRESS = {
    "upload_received": 0.1,
    "chunking_text": 0.25,
    "extracting_images": 0.4,
    "storing_chunks": 0.55,
    "extracting_entities": 0.7,
    "writing_graphdb": 0.85,
    "completed": 1.0,
    "failed": 1.0,
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
    st.session_state.jobs = {}

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
                "stage": result.get("stage", "upload_received"),
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
        col1, col2, col3 = st.columns([3, 4, 2])
        
        col1.write(f"**{job['filename']}**")

        current_stage = job.get("stage", "upload_received")
        stage_display = STAGE_LABELS.get(current_stage, current_stage.replace("_", " ").title())
        
        with col2:
            st.write(f"{icon} `{job['status']}` ➔ *{stage_display}*")
            progress_val = STAGE_PROGRESS.get(current_stage, 0.0)
            
            if job["status"] == "failed":
                st.progress(1.0)
            else:
                st.progress(progress_val)

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
                    job["stage"] = updated.get("stage", job.get("stage"))
                    job["document_id"] = updated.get("document_id")
                    job["num_chunks"] = updated.get("num_chunks")
                    job["error"] = updated.get("error")
        time.sleep(1)
        st.rerun()