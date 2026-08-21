import uuid


class NotificationDeliveryResult:
    def __init__(self, *, provider, provider_message_id=""):
        self.provider = provider
        self.provider_message_id = provider_message_id


class BaseNotificationProvider:
    provider_name = "base"

    def send(self, notification):
        raise NotImplementedError


class LocalNotificationProvider(BaseNotificationProvider):
    provider_name = "local"

    def send(self, notification):
        return NotificationDeliveryResult(
            provider=self.provider_name,
            provider_message_id=f"local_{uuid.uuid4().hex}",
        )
