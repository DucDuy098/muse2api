# Single image: FastAPI backend + the Next.js static export served from the
# same process (no separate Nginx container — this box runs everything
# behind Coolify's own Traefik, one container per Coolify "Application").

FROM node:20-slim AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Same-origin in production: Traefik serves API and static files under one
# domain, so the frontend calls relative paths — no NEXT_PUBLIC_API_BASE
# (.env.local is dev-only and excluded via .dockerignore).
RUN npm run build

FROM python:3.11-slim AS backend
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium fonts-liberation fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# frontend/ source isn't needed in the final image — only its built output
# (copied below from the frontend stage).
RUN rm -rf frontend

COPY --from=frontend /src/out ./frontend/out

ENV MUSE2API_CHROMIUM=/usr/bin/chromium \
    MUSE2API_HOST=0.0.0.0 \
    MUSE2API_PORT=18610 \
    PYTHONUNBUFFERED=1

EXPOSE 18610
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "18610"]
