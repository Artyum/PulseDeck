FROM node:22-alpine AS frontend
WORKDIR /build
RUN apk upgrade --no-cache
COPY package.json package-lock.json ./
RUN npm ci
COPY frontend ./frontend
COPY scripts/vendor-static.sh scripts/vendor-static.sh
RUN sh scripts/vendor-static.sh
RUN npx tailwindcss -i frontend/static/css/tailwind.css -o frontend/static/css/app.css --minify
RUN npm run js:build

FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools \
    && pip install --no-cache-dir --upgrade -r requirements.txt \
    && pip uninstall -y pip setuptools wheel

ARG APT_REFRESH=0
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY . .
COPY --from=frontend /build/frontend/static/css/app.css frontend/static/css/app.css
COPY --from=frontend /build/frontend/static/js/editor.bundle.js frontend/static/js/editor.bundle.js
COPY --from=frontend /build/frontend/static/vendor frontend/static/vendor

RUN chmod +x deploy/entrypoint.sh deploy/entrypoint_worker.sh deploy/entrypoint_migrate.sh
EXPOSE 8000
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
