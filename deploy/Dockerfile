FROM node:22-alpine AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY frontend ./frontend
RUN npx tailwindcss -i frontend/static/css/tailwind.css -o frontend/static/css/app.css --minify

FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=frontend /build/frontend/static/css/app.css frontend/static/css/app.css
RUN chmod +x deploy/entrypoint.sh deploy/entrypoint_mail.sh
EXPOSE 8000
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
