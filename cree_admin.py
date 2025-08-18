import asyncio
from database import db_helper, init_db


SECRET_KEY = "votre_clé_secrète_ici"  # Changez ceci en production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


async def main():
    # Initialiser la DB si pas encore fait
    await init_db()
    
    # Demander les informations admin
    username = input("Nom d'utilisateur admin: ")
    password = input("Mot de passe admin: ")
    
    try:
        user_id = await db_helper.create_admin_user(username, password)
        print(f"✅ Admin créé avec succès! ID: {user_id}")
    except ValueError as e:
        print(f"❌ Erreur: {e}")

if __name__ == "__main__":
    asyncio.run(main())