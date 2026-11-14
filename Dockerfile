# One container: the API + the built web app + Chromium for the customers' browsing.
# Build:  docker build -t customer-sim .        Run: see deploy/docker-compose.yml

# ---- web app ----
FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ---- API (Playwright's image already has Chromium and its system libraries) ----
FROM mcr.microsoft.com/playwright/python:v1.65.2-noble
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_BREAK_SYSTEM_PACKAGES=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY server.py ./
COPY b2a/ ./b2a/
COPY fixtures/ ./fixtures/
COPY --from=web /web/dist ./web/dist
EXPOSE 4620
# One worker on purpose: running simulations live in this process's memory.
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "4620", "--workers", "1", "--timeout-keep-alive", "75"]
