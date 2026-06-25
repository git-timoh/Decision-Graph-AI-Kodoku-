# Stage 1 — build the static UI
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build   # -> /web/out

# Stage 2 — Python app serving API + UI on one port
FROM python:3.12-slim
WORKDIR /app
COPY backend/ ./
# bundle the prebuilt UI where web_dir() looks first
COPY --from=web /web/out ./kodoku/_web
RUN pip install --no-cache-dir --retries 5 --timeout 120 .
ENV DATABASE_URL=sqlite+aiosqlite:////data/kodoku.db
VOLUME /data
EXPOSE 8000
CMD ["kodoku", "--host", "0.0.0.0", "--no-browser"]
