# Streamlit Ingestion GUI

A lightweight Streamlit interface to upload and monitor PDF document ingestion jobs.

## Setup

```bash
pip install -r gui/requirements.txt
```

## Run

Make sure the ingestion API is running (default: `http://localhost:8000`).

```bash
streamlit run gui/streamlit_app.py
```

You can point to a different API base by editing the `API_BASE` constant at the top of `streamlit_app.py`.
