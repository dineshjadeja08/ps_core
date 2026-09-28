from rest_framework import serializers

from apps.notifications.models import DeviceToken, Notification


class NotificationSerializer(serializers.ModelSerializer):
    recipient_phone = serializers.CharField(source="recipient.phone_number", read_only=True)
    booking_number = serializers.CharField(source="booking.booking_number", read_only=True)

    class Meta:
        model = Notification
        fields = (
            "id",
            "recipient",
            "recipient_phone",
            "booking",
            "booking_number",
            "event",
            "channel",
            "status",
            "title",
            "message",
            "provider",
            "provider_message_id",
            "send_attempts",
            "payload",
            "error_message",
            "sent_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "recipient_phone",
            "booking_number",
            "provider",
            "provider_message_id",
            "send_attempts",
            "error_message",
            "sent_at",
            "created_at",
            "updated_at",
        )


class NotificationActionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True)


class DeviceTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceToken
        fields = ("token", "platform")
        extra_kwargs = {"token": {"validators": []}}

    def validate_token(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("FCM token is required.")
        if len(value) > 4096:
            raise serializers.ValidationError("FCM token is too long.")
        return value
