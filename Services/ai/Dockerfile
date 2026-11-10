FROM python:3.12-slim

# System deps:
#   build-essential  — native Python extension compilation (grpcio, etc.)
#   git              — clone repositories for build runs
#   curl             — Docker CLI install + health probes
#   Docker CLI       — talk to the host Docker daemon via the mounted socket
#                      (we install only the CLI binary, not the daemon)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        curl \
        ca-certificates \
        gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
       | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
       https://download.docker.com/linux/debian bookworm stable" \
       > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Configure git globally: never prompt for credentials, set a sensible identity
# GIT_TERMINAL_PROMPT is an env var — set it both ways so nothing ever blocks
RUN git config --global user.email "forgeai@forgeai.local" \
    && git config --global user.name "ForgeAI" \
    && git config --global credential.helper "" \
    && git config --global core.askPass ""
ENV GIT_TERMINAL_PROMPT=0

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002", "--reload"]
