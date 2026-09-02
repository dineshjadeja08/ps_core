from decimal import Decimal

from django.db import transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.catalogue.models import AdvancePaymentType, Service, ServiceCategory, ServiceImage


MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def validate_uploaded_image(file_obj):
    if file_obj is None:
        return file_obj
    content_type = getattr(file_obj, "content_type", "")
    if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise serializers.ValidationError("Upload a JPEG, PNG, or WebP image.")
    if getattr(file_obj, "size", 0) > MAX_IMAGE_SIZE_BYTES:
        raise serializers.ValidationError("Image size cannot exceed 5 MB.")
    return file_obj


class ServiceCategorySerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ServiceCategory
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "image_url",
            "display_order",
        )

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get("request")
            url = obj.image.url
            return request.build_absolute_uri(url) if request else url
        return obj.image_url


class ServiceListSerializer(serializers.ModelSerializer):
    category = ServiceCategorySerializer(read_only=True)
    cover_image = serializers.ImageField(read_only=True)
    effective_price = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = (
            "id",
            "category",
            "name",
            "slug",
            "short_description",
            "base_price",
            "selling_price",
            "effective_price",
            "advance_amount",
            "estimated_duration_minutes",
            "cover_image",
            "is_featured",
            "is_popular",
            "display_order",
        )

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_effective_price(self, obj):
        return obj.effective_price


class ServiceDetailSerializer(ServiceListSerializer):
    class Meta(ServiceListSerializer.Meta):
        fields = ServiceListSerializer.Meta.fields + (
            "description",
            "whats_included",
            "whats_excluded",
            "important_notes",
        )


class AdminServiceCategorySerializer(serializers.ModelSerializer):
    image = serializers.ImageField(required=False, allow_empty_file=False, validators=[validate_uploaded_image])
    image_url = serializers.SerializerMethodField()
    external_image_url = serializers.URLField(source="image_url", required=False, allow_blank=True, write_only=True)

    class Meta:
        model = ServiceCategory
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "image",
            "image_url",
            "external_image_url",
            "display_order",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get("request")
            url = obj.image.url
            return request.build_absolute_uri(url) if request else url
        return obj.image_url


class ServiceImageSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(validators=[validate_uploaded_image])

    class Meta:
        model = ServiceImage
        fields = (
            "id",
            "service",
            "image",
            "alt_text",
            "display_order",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "service", "created_at", "updated_at")


class AdminServiceSerializer(serializers.ModelSerializer):
    category_detail = ServiceCategorySerializer(source="category", read_only=True)
    cover_image = serializers.ImageField(required=False, allow_empty_file=False, validators=[validate_uploaded_image])
    images = ServiceImageSerializer(many=True, read_only=True)
    effective_price = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = (
            "id",
            "category",
            "category_detail",
            "name",
            "slug",
            "short_description",
            "description",
            "whats_included",
            "whats_excluded",
            "important_notes",
            "base_price",
            "selling_price",
            "effective_price",
            "advance_payment_type",
            "advance_payment_value",
            "advance_amount",
            "estimated_duration_minutes",
            "cover_image",
            "images",
            "is_featured",
            "is_popular",
            "is_active",
            "display_order",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "effective_price", "advance_amount", "created_at", "updated_at")

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_effective_price(self, obj):
        return obj.effective_price

    def validate_cover_image(self, value):
        return validate_uploaded_image(value)

    def validate(self, attrs):
        instance = self.instance
        base_price = attrs.get("base_price", getattr(instance, "base_price", None))
        selling_price = attrs.get("selling_price", getattr(instance, "selling_price", None))
        advance_type = attrs.get(
            "advance_payment_type",
            getattr(instance, "advance_payment_type", AdvancePaymentType.FIXED),
        )
        advance_value = attrs.get("advance_payment_value", getattr(instance, "advance_payment_value", None))
        if advance_value is None:
            advance_value = getattr(instance, "advance_amount", Decimal("0.00")) if instance else Decimal("0.00")

        effective_price = selling_price if selling_price is not None else base_price
        if base_price is not None and base_price < Decimal("0.00"):
            raise serializers.ValidationError({"base_price": "Base price cannot be negative."})
        if selling_price is not None and selling_price < Decimal("0.00"):
            raise serializers.ValidationError({"selling_price": "Selling price cannot be negative."})
        if advance_value < Decimal("0.00"):
            raise serializers.ValidationError({"advance_payment_value": "Advance payment value cannot be negative."})
        if advance_type == AdvancePaymentType.PERCENTAGE and advance_value > Decimal("100.00"):
            raise serializers.ValidationError({"advance_payment_value": "Advance percentage cannot exceed 100."})
        if advance_type == AdvancePaymentType.FIXED and effective_price is not None and advance_value > effective_price:
            raise serializers.ValidationError({"advance_payment_value": "Advance amount cannot exceed service price."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        validated_data = self._with_synced_advance(validated_data)
        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        validated_data = self._with_synced_advance(validated_data, instance=instance)
        return super().update(instance, validated_data)

    def _with_synced_advance(self, validated_data, instance=None):
        base_price = validated_data.get("base_price", getattr(instance, "base_price", None))
        selling_price = validated_data.get("selling_price", getattr(instance, "selling_price", None))
        advance_type = validated_data.get(
            "advance_payment_type",
            getattr(instance, "advance_payment_type", AdvancePaymentType.FIXED),
        )
        fallback_advance = getattr(instance, "advance_amount", Decimal("0.00")) if instance else Decimal("0.00")
        advance_value = validated_data.get("advance_payment_value", getattr(instance, "advance_payment_value", None))
        if advance_value is None:
            advance_value = fallback_advance
        effective_price = selling_price if selling_price is not None else base_price

        if advance_type == AdvancePaymentType.PERCENTAGE:
            validated_data["advance_amount"] = (effective_price * advance_value / Decimal("100.00")).quantize(
                Decimal("0.01")
            )
        else:
            validated_data["advance_amount"] = advance_value
        validated_data["advance_payment_value"] = advance_value
        return validated_data
