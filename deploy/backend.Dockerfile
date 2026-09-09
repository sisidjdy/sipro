FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    build-essential libffi-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

# Paket internal Emergent (emergentintegrations + litellm wheel privat) tidak dipakai kode
# backend dan tidak tersedia di PyPI publik → dibuang dari daftar sebelum install.
COPY backend/requirements.txt ./requirements.txt
RUN grep -vE '^(emergentintegrations|litellm)' requirements.txt > /tmp/req.txt \
    && pip install --upgrade pip \
    && pip install -r /tmp/req.txt

COPY backend/ ./

EXPOSE 8001
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
