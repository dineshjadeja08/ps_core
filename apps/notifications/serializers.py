from rest_framework import serializers

from apps.notifications.models import Notification, PushPlatform


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


class PushDeviceSerializer(serializers.Serializer):
    token = serializers.RegexField(r"^Expo(nent)?PushToken\[[^\]]+\]$", max_length=255, error_messages={"invalid": "Not an Expo push token."})
    platform = serializers.ChoiceField(choices=PushPlatform.choices)
    app = serializers.ChoiceField(choices=(("partner", "Partner app"), ("customer", "Customer app")), default="partner")
