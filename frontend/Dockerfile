# ══════════════════════════════════════════════════════════════
# Dockerfile — Frontend Dash (GTA Digital Twin)
# ══════════════════════════════════════════════════════════════
FROM python:3.11.9-slim

LABEL maintainer="GTA Digital Twin"
LABEL description="Interface de supervision SCADA — Dash"

# Variables d'environnement
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DASH_DEBUG=false \
    BACKEND_URL=http://backend:8000

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
    CMD curl -f http://localhost:8050/ || exit 1

# Port exposé
EXPOSE 8050

# Point d'entrée
CMD ["python", "app.py"]