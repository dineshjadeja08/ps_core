from rest_framework import serializers

from apps.catalogue.models import Service
from apps.locations.models import Address, ServiceArea, normalize_postal_code


class ServiceAreaCheckSerializer(serializers.Serializer):
    postal_code = serializers.CharField()


class ServiceAreaCheckResponseSerializer(serializers.Serializer):
    postal_code = serializers.CharField()
    is_supported = serializers.BooleanField()
    service_area = serializers.DictField(allow_null=True)


class ReverseGeocodeQuerySerializer(serializers.Serializer):
    lat = serializers.DecimalField(max_digits=10, decimal_places=7, min_value=-90, max_value=90, coerce_to_string=False)
    lng = serializers.DecimalField(max_digits=10, decimal_places=7, min_value=-180, max_value=180, coerce_to_string=False)


class AutocompleteQuerySerializer(serializers.Serializer):
    input = serializers.CharField(min_length=3, max_length=160, trim_whitespace=True)
    lat = serializers.DecimalField(max_digits=10, decimal_places=7, min_value=-90, max_value=90, coerce_to_string=False, required=False)
    lng = serializers.DecimalField(max_digits=10, decimal_places=7, min_value=-180, max_value=180, coerce_to_string=False, required=False)
    city = serializers.CharField(max_length=80, trim_whitespace=True, required=False, allow_blank=True)

    def validate(self, attrs):
        if ("lat" in attrs) != ("lng" in attrs):
            raise serializers.ValidationError("lat and lng must be supplied together.")
        return attrs


class NormalizedAddressSerializer(serializers.Serializer):
    formatted_address = serializers.CharField(allow_blank=True)
    house_number = serializers.CharField(allow_blank=True)
    street = serializers.CharField(allow_blank=True)
    locality = serializers.CharField(allow_blank=True)
    city = serializers.CharField(allow_blank=True)
    state = serializers.CharField(allow_blank=True)
    pincode = serializers.CharField(allow_blank=True)
    country = serializers.CharField(allow_blank=True)
    latitude = serializers.FloatField(allow_null=True)
    longitude = serializers.FloatField(allow_null=True)
    supported_city = serializers.BooleanField()
    serviceable = serializers.BooleanField()


class AddressSuggestionSerializer(NormalizedAddressSerializer):
    id = serializers.CharField()
    description = serializers.CharField()
    main_text = serializers.CharField()
    secondary_text = serializers.CharField(allow_blank=True)


class AutocompleteResponseSerializer(serializers.Serializer):
    suggestions = AddressSuggestionSerializer(many=True)


class ServiceAreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceArea
        fields = ("id", "name", "city", "state", "country", "postal_code")


class AdminServiceAreaSerializer(serializers.ModelSerializer):
    services = serializers.SerializerMethodField()
    service_ids = serializers.PrimaryKeyRelatedField(
        source="services",
        queryset=Service.objects.all(),
        many=True,
        required=False,
        write_only=True,
    )

    class Meta:
        model = ServiceArea
        fields = (
            "id",
            "name",
            "city",
            "state",
            "country",
            "postal_code",
            "is_active",
            "services",
            "service_ids",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def get_services(self, obj):
        return [
            {"id": str(service.id), "name": service.name, "slug": service.slug}
            for service in obj.services.all().order_by("category__display_order", "display_order", "name")
        ]

    def validate_postal_code(self, value):
        normalized = normalize_postal_code(value)
        if not normalized:
            raise serializers.ValidationError("Postal code is required.")
        return normalized

    def create(self, validated_data):
        selected_services = validated_data.pop("services", None)
        validated_data["services_configured"] = selected_services is not None
        area = super().create(validated_data)
        area.services.set(selected_services if selected_services is not None else Service.objects.filter(is_active=True))
        return area

    def update(self, instance, validated_data):
        if "services" in validated_data:
            validated_data["services_configured"] = True
        return super().update(instance, validated_data)


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
