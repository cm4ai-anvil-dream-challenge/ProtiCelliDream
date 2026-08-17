FROM python:3.11-slim

WORKDIR /app

# Copy dependency file first, install deps — before copying the rest of the code.
# This lets Docker cache this layer, so editing your Python files later
# doesn't force a full dependency reinstall on every rebuild.
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Now copy the actual code
COPY proticelli/ ./proticelli/
COPY pipeline_checks.py .

CMD ["python3", "-c", "print('ProtiCelli image built successfully')"]
