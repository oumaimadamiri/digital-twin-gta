"""
config.py — Configuration centrale du frontend Dash
Adapté pour Docker et WebSockets :
- BACKEND : URL interne (Frontend -> Backend via Docker Network)
- PUBLIC_BACKEND : URL externe (Navigateur -> Backend via localhost/IP)
"""
import os

# URL interne pour les requêtes Python (requêtes côté serveur)
# Sous Docker : http://backend:8000
# En local : http://localhost:8000
BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")

# URL publique pour le WebSocket (requêtes côté client/navigateur)
# Sous Docker : http://localhost:8000 (car le navigateur accède via l'hôte)
# En local : http://localhost:8000
PUBLIC_BACKEND = os.getenv("PUBLIC_BACKEND_URL", "http://localhost:8000").rstrip("/")
