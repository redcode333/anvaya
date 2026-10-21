# Single image: builds the React frontend, then serves it plus the Flask API with gunicorn.
FROM node:20-alpine AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
COPY backend/tests/fixtures /app/backend/tests/fixtures
COPY backend/anvaya/data /app/backend/anvaya/data
RUN npm run build

FROM python:3.12-slim
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY data/ /app/data/
COPY --from=web /app/frontend/dist /app/frontend/dist
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin anvaya && mkdir -p /app/var && chown anvaya /app/var
# HOME=/tmp: the root filesystem is read-only in Kubernetes; /tmp is the only writable scratch space.
ENV ANVAYA_DB=/app/var/anvaya.db PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
USER 10001
EXPOSE 5000
# One worker + threads: prometheus_client counters are per-process, so a single process keeps /metrics complete.
CMD ["sh", "-c", "python -m anvaya.manage init && gunicorn -w 1 --threads 8 -b 0.0.0.0:5000 wsgi:app"]
