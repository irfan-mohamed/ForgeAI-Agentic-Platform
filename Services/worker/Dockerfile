FROM python:3.12-slim

# Install git (required for GitPython cloning)
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create clone workspace directory
RUN mkdir -p /tmp/forgeai_worker_clones

# Run as non-root user for security
RUN useradd -m -u 1000 worker && chown -R worker:worker /app /tmp/forgeai_worker_clones
USER worker

# Entry point — run the async worker process
CMD ["python", "-m", "app.main"]
