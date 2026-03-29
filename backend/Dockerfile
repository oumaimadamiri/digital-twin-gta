# ══════════════════════════════════════════════════════════════
# Dockerfile — Backend FastAPI (GTA Digital Twin)
# ══════════════════════════════════════════════════════════════
FROM python:3.11.9-slim

LABEL maintainer="GTA Digital Twin"
LABEL description="API de supervision et simulation — FastAPI"

# Variables d'environnement
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AI_TRAIN_ON_STARTUP=true \
    REDIS_HOST=redis \
    REDIS_PORT=6379

WORKDIR /app

# Dépendances système minimales
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code source
COPY . .

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Port exposé
EXPOSE 8000

# Point d'entrée
CMD ["python", "main.py"]
