# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS frontend
WORKDIR /src
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM golang:1.25-bookworm AS tools
ENV GOBIN=/out GOTOOLCHAIN=auto
RUN apt-get update && apt-get install -y --no-install-recommends libpcap-dev && rm -rf /var/lib/apt/lists/*
COPY scripts/install_container_tools.sh /tmp/install_container_tools.sh
RUN bash /tmp/install_container_tools.sh

FROM python:3.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates curl git nmap dnsutils coreutils jq libpcap0.8 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=tools /out/ /usr/local/bin/
COPY vendor/claude-bug-bounty/ /opt/claude-bug-bounty/
RUN test -f /opt/claude-bug-bounty/tools/recon_engine.sh
COPY backend/ ./backend/
COPY --from=frontend /src/dist/ ./backend/static/
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x /app/entrypoint.sh
ENV BBASM_BBROOT=/opt/claude-bug-bounty BBASM_TOOLS_SUBDIR=tools \
    BBASM_DATA=/app/data BBASM_TARGETS=/app/targets BBASM_STATIC=/app/backend/static \
    BBASM_BIND=0.0.0.0 BBASM_PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=150s CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('BBASM_PORT','8000')+'/api/health',timeout=4)" || exit 1
ENTRYPOINT ["/app/entrypoint.sh"]
