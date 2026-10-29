FROM python:3.12-slim-bullseye

WORKDIR /app

COPY requirements.txt .
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    update-ca-certificates && \
    pip install --no-cache-dir -r requirements.txt

# Копируем только нужные файлы (не весь репозиторий)
COPY app/ ./app/
COPY api/* ./api/

ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
