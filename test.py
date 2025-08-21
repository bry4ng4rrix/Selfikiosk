import os
import ovh
from dotenv import load_dotenv

# Charger les variables .env
load_dotenv()

# Debug : afficher la valeur chargée
print("Endpoint chargé:", os.getenv("OVH_ENDPOINT"))

client = ovh.Client(
    endpoint=os.getenv("OVH_ENDPOINT", "ovh-eu"),
    application_key=os.getenv("OVH_APP_KEY"),
    application_secret=os.getenv("OVH_APP_SECRET"),
    consumer_key=os.getenv("OVH_CONSUMER_KEY"),
)
print("Welcome", client.get('/me')['firstname'])

# Exemple: lister les services SMS
services = client.get('/sms')
print("Services disponibles:", services)

if services:
    res = client.post(f"/sms/{services[0]}/jobs",
                      sender="FoodAndBeer",
                      message="Test SMS via OVH API",
                      receivers=["+33600000000"])
    print("Résultat envoi SMS:", res)

