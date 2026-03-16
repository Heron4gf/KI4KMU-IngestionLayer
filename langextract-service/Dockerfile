FROM python:3.10-slim
WORKDIR /app
RUN pip install --no-cache-dir langextract fastapi uvicorn[standard]
COPY server.py .
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8003"]
