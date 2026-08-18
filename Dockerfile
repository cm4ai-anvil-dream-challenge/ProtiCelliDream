FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY proticelli/ ./proticelli/
COPY pipeline_checks.py .
COPY run_inference.py .

ENTRYPOINT ["python3", "run_inference.py"]