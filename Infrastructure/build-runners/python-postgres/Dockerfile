FROM postgres:16-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home runner
WORKDIR /workspace
COPY requirements.txt .
RUN python3 -m venv /opt/test-venv \
    && /opt/test-venv/bin/pip install --no-cache-dir -r requirements.txt httpx

ARG APP_IMPORT=app.main:app
ARG HEALTH_PATH=/health
ARG PYTEST_IGNORE=
ENV PATH="/opt/test-venv/bin:/usr/lib/postgresql/16/bin:$PATH" \
    APP_IMPORT=$APP_IMPORT HEALTH_PATH=$HEALTH_PATH PYTEST_IGNORE=$PYTEST_IGNORE \
    HOME=/tmp PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY run.sh /usr/local/bin/forgeai-test
RUN sed -i 's/\r$//' /usr/local/bin/forgeai-test
USER 10001:10001
ENTRYPOINT ["/bin/sh", "/usr/local/bin/forgeai-test"]
