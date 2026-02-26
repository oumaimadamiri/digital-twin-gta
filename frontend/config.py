"""
config.py — Configuration centrale du frontend Dash

Actuellement :
- BACKEND : URL de l'API FastAPI (défaut http://localhost:8000)
  Peut être surchargée via la variable d'environnement BACKEND_URL
  (déjà définie dans docker-compose pour pointer sur http://backend:8000).
"""

import os

BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")

