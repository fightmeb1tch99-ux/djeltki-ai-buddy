# Один образ: сначала собираем интерфейс (React + TypeScript), потом кладём его в Flask-приложение.
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN node build.mjs

FROM python:3.12-slim AS app
WORKDIR /app
COPY backend/requirements.txt backend/requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY backend/ ./
COPY --from=frontend /frontend/dist /app/static
ENV STATIC_DIR=/app/static \
    DATABASE_PATH=/data/ai_buddy.db \
    PYTHONUNBUFFERED=1
RUN mkdir -p /data
EXPOSE 8080
CMD ["gunicorn", "-b", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "wsgi:app"]
