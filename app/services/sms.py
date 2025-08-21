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
        # Re-raise the exception to let Dramatiq handle retries
        raise
