from rest_framework import serializers

from apps.locations.models import Address, ServiceArea, normalize_postal_code


class ServiceAreaCheckSerializer(serializers.Serializer):
    postal_code = serializers.CharField()


class ServiceAreaCheckResponseSerializer(serializers.Serializer):
    postal_code = serializers.CharField()
    is_supported = serializers.BooleanField()
    service_area = serializers.DictField(allow_null=True)


class ServiceAreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceArea
        fields = ("id", "name", "city", "state", "country", "postal_code")


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = (
            "id",
            "label",
            "recipient_name",
            "phone",
            "address_line_1",
            "address_line_2",
            "landmark",
            "locality",
            "city",
            "state",
            "postal_code",
            "country",
            "latitude",
            "longitude",
            "is_default",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_postal_code(self, value):
        normalized = normalize_postal_code(value)
        if not normalized:
            raise serializers.ValidationError("Postal code is required.")
        return normalized

    def validate_latitude(self, value):
        if value is not None and not (-90 <= value <= 90):
            raise serializers.ValidationError("Latitude must be between -90 and 90.")
        return value

    def validate_longitude(self, value):
        if value is not None and not (-180 <= value <= 180):
            raise serializers.ValidationError("Longitude must be between -180 and 180.")
        return value

    def create(self, validated_data):
        validated_data["customer"] = self.context["request"].user
        return super().create(validated_data)
