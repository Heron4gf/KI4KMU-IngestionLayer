FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# State directory is expected to be bind-mounted at runtime.
# This ensures the folder exists even without a mount (e.g. local dev).
RUN mkdir -p /app/state

CMD ["python", "run_eval.py"]
