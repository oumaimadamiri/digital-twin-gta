# Digital Twin GTA — Plateforme de Supervision et Simulation

Ce projet est un **Jumeau Numérique (Digital Twin)** d'un Groupe Turbo-Alternateur (GTA), conçu pour la supervision industrielle, la simulation de scénarios critiques et l'analyse prédictive via l'Intelligence Artificielle.

---

## 🚀 Fonctionnalités Clés

- **Supervision Temps Réel** : Visualisation des paramètres critiques (pressions, températures, débits, puissance) via un synoptique dynamique et des gauges interactives.
- **Simulation de Scénarios** : Bac à sable (sandbox) permettant de simuler des pannes ou des dérives (chute de pression, surchauffe, survitesse) sans affecter les données réelles.
- **Intelligence Artificielle** : 
    - **Autoencodeur** : Détection d'anomalies en comparant l'état actuel au comportement nominal appris.
    - **LSTM** : Prédiction de l'évolution des paramètres à court terme.
    - **XGBoost** : Estimation de la Durée de Vie Résiduelle (RUL - Remaining Useful Life).
- **Gestion des Alertes** : Système de détection automatique des dépassements de seuils avec journalisation.
- **Analyse Historique** : Visualisation des tendances passées et export de données.

---

## 🏗️ Architecture Technique

Le projet repose sur une architecture moderne découplée :

- **Backend (API)** :
    - [FastAPI](https://fastapi.tiangolo.com/) (Python) pour une API haute performance.
    - [Redis](https://redis.io/) pour le cache temps réel et la communication entre services.
    - [SQLite](https://www.sqlite.org/) pour la persistance des historiques et des alertes.
- **Frontend (Interface)** :
    - [Dash by Plotly](https://dash.plotly.com/) pour une interface réactive et analytique.
    - [Plotly.py](https://plotly.com/python/) pour les graphiques interactifs.
- **IA & Physique** :
    - Modélisation thermodynamique multi-étages.
    - Frameworks : [TensorFlow](https://www.tensorflow.org/), [XGBoost](https://xgboost.readthedocs.io/), [Scikit-learn](https://scikit-learn.org/).

---

## 🛠️ Installation et Lancement

### Option 1 : Docker (Recommandé)

Assurez-vous d'avoir [Docker](https://www.docker.com/) et [Docker Compose](https://docs.docker.com/compose/) installés.

```bash
# Cloner le dépôt
git clone <url-du-repo>
cd digital-twin-gta

# Lancer l'ensemble des services
docker-compose up --build
```

- **Frontend** : `http://localhost:8050`
- **Backend API** : `http://localhost:8000`
- **Documentation API (Swagger)** : `http://localhost:8000/docs`

### Option 2 : Installation Manuelle (Développement)

#### Prérequis
- Python 3.10+
- Redis Server (doit être lancé sur le port 6379)

#### Configuration du Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Ou venv\Scripts\activate sur Windows
pip install -r requirements.txt
python main.py
```

#### Configuration du Frontend
```bash
cd frontend
python -m venv venv
source venv/bin/activate  # Ou venv\Scripts\activate sur Windows
pip install -r requirements.txt
python app.py
```

---

## ⚙️ Configuration

Les variables d'environnement peuvent être configurées dans un fichier `.env` à la racine :

- `API_HOST` / `API_PORT` : Adresse et port du backend.
- `REDIS_HOST` / `REDIS_PORT` : Connexion au cache Redis.
- `AI_TRAIN_ON_STARTUP` : `true`/`false` pour entraîner les modèles au démarrage.
- `NOISE_LEVEL` : Niveau de bruit blanc ajouté à la simulation.

---

## 📊 Paramètres Nominaux

La simulation se base sur les spécifications industrielles suivantes :
- **Pression HP** : 60 bar
- **Température HP** : 470 °C
- **Vitesse Turbine** : 6420 RPM
- **Puissance Active** : 24 MW
- **Rendement** : 92%

---

## 📝 Auteurs

Développé dans le cadre du projet **Digital Twin GTA**.