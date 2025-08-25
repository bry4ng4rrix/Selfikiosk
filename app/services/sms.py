import ovh
import dramatiq
from ..core.config import settings

@dramatiq.actor
def send_sms_task(phone: str, message: str):
    """
    Sends an SMS using the OVH API as a background task.
    """
    client = ovh.Client(
        endpoint=settings.OVH_ENDPOINT,
        application_key=settings.OVH_APP_KEY,
        application_secret=settings.OVH_APP_SECRET,
        consumer_key=settings.OVH_CONSUMER_KEY
    )
    sms_service_path = f"/sms/{settings.SMS_SERVICE_NAME}/jobs"
    try:
        result = client.post(
            sms_service_path,
            message=message,
            receivers=[phone],
            sender=settings.SMS_SENDER,
            noStopClause=True
        )
        print(f"SMS sent successfully: {result}")
    except ovh.exceptions.APIError as e:
        print(f"OVH API Error during SMS sending: {e}")

        raise

def send_sms_now(phone: str, message: str):

    client = ovh.Client(
        endpoint=settings.OVH_ENDPOINT,
        application_key=settings.OVH_APP_KEY,
        application_secret=settings.OVH_APP_SECRET,
        consumer_key=settings.OVH_CONSUMER_KEY
    )

    try:
        sms_services = client.get('/sms')

        if settings.SMS_SERVICE_NAME not in sms_services:
            available_services = ", ".join(sms_services) if sms_services else "Aucun"
            error_msg = f"Service SMS '{settings.SMS_SERVICE_NAME}' introuvable. Services disponibles: {available_services}"
            raise ovh.exceptions.APIError(error_msg)

        service_info = client.get(f'/sms/{settings.SMS_SERVICE_NAME}')

        try:
            jobs = client.get(f'/sms/{settings.SMS_SERVICE_NAME}/jobs')
        except ovh.exceptions.Forbidden:
            error_msg = "Permissions insuffisantes pour accéder aux jobs SMS"
            raise ovh.exceptions.APIError(error_msg)

        sms_service_path = f"/sms/{settings.SMS_SERVICE_NAME}/jobs"

        result = client.post(
            sms_service_path,
            message=message,
            receivers=[phone],
            sender=settings.SMS_SENDER,
            noStopClause=True
        )

        print(f"✅ SMS envoyé avec succès: {result}")
        return result

    except ovh.exceptions.InvalidCredential as e:
        error_msg = f"Clés API OVH invalides ou expirées: {e}"

        raise ovh.exceptions.APIError(error_msg)

    except ovh.exceptions.Forbidden as e:
        error_msg = f"Accès refusé - permissions insuffisantes: {e}"

        raise ovh.exceptions.APIError(error_msg)

    except ovh.exceptions.APIError as e:
        print(f"❌ Erreur API OVH: {e}")

        raise

    except Exception as e:
        error_msg = f"Erreur inattendue: {e}"
        print(f"❌ {error_msg}")
        raise ovh.exceptions.APIError(error_msg)