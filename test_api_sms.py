import os
import ovh
from dotenv import load_dotenv

load_dotenv()

print("Endpoint chargé:", os.getenv("OVH_ENDPOINT"))

client = ovh.Client(
    endpoint=os.getenv("OVH_ENDPOINT", "ovh-eu"),
    application_key=os.getenv("OVH_APP_KEY"),
    application_secret=os.getenv("OVH_APP_SECRET"),
    consumer_key=os.getenv("OVH_CONSUMER_KEY"),
)
print("Welcome", client.get('/me')['firstname'])

