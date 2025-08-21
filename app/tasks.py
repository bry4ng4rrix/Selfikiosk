import dramatiq
from dramatiq.brokers.redis import RedisBroker
from .core.config import settings

# Configure the Redis broker
redis_broker = RedisBroker(url=settings.REDIS_URL)
dramatiq.set_broker(redis_broker)

# Import modules containing tasks (actors) so that Dramatiq can discover them.
from .services import sms, sync, cleanup
