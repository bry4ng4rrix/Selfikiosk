# FastAPI Admin Authentication

Une API FastAPI simple pour l'enregistrement et l'authentification d'un administrateur utilisant un email et un mot de passe. L'application utilise SQLite pour le stockage des données, `bcrypt` pour le hachage des mots de passe, et des tokens JWT pour l'authentification sécurisée.

## Prérequis

- Python 3.8+
- FastAPI
- Uvicorn
- Autres dépendances : `python-jose[cryptography]`, `passlib[bcrypt]`, `python-multipart`

## Installation

1. Clonez ce dépôt ou téléchargez le code source.

2. Créez un environnement virtuel et activez-le :
   ```bash
   python -m venv venv
   source venv/bin/activate  # Sur Windows : venv\Scripts\activate