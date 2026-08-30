from rest_framework import serializers

from apps.audit.models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_phone = serializers.CharField(source="actor.phone_number", read_only=True)

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "actor",
            "actor_phone",
            "action",
            "resource_type",
            "resource_id",
            "request_id",
            "ip_address",
            "user_agent",
            "metadata",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
