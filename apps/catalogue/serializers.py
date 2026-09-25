from decimal import Decimal

from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from cloudinary.exceptions import Error as CloudinaryError
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.catalogue.models import AdvancePaymentType, Package, PackageItem, Service, ServiceCategory, ServiceImage


MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def raise_drf_validation(exc):
    if isinstance(exc, DjangoValidationError):
        details = exc.message_dict if hasattr(exc, "message_dict") else {"non_field_errors": exc.messages}
        raise serializers.ValidationError(details) from exc
    raise serializers.ValidationError(
        {"non_field_errors": ["This change conflicts with an existing catalogue record."]}
    ) from exc


def validate_uploaded_image(file_obj):
    if file_obj is None:
        return file_obj
    content_type = getattr(file_obj, "content_type", "")
    if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise serializers.ValidationError("Upload a JPEG, PNG, or WebP image.")
    if getattr(file_obj, "size", 0) > MAX_IMAGE_SIZE_BYTES:
        raise serializers.ValidationError("Image size cannot exceed 5 MB.")
    return file_obj


def raise_media_storage_validation(exc):
    raise serializers.ValidationError(
        {"image": ["Image storage rejected the upload. Verify the Cloudinary cloud name, API key, and API secret."]}
    ) from exc


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
    landing_thumbnail = serializers.ImageField(read_only=True)
    popup_cover_image = serializers.ImageField(read_only=True)
    popup_content_image = serializers.ImageField(read_only=True)
    list_image = serializers.ImageField(read_only=True)
    effective_price = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = (
            "id",
            "category",
            "name",
            "slug",
            "short_description",
            "whats_included",
            "landing_group",
            "base_price",
            "selling_price",
            "effective_price",
            "advance_payment_type",
            "advance_payment_value",
            "advance_amount",
            "training_fee",
            "training_fee_per_unit",
            "estimated_duration_minutes",
            "cover_image",
            "landing_thumbnail",
            "popup_cover_image",
            "popup_content_image",
            "list_image",
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

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except CloudinaryError as exc:
            raise_media_storage_validation(exc)
        except (DjangoValidationError, IntegrityError) as exc:
            raise_drf_validation(exc)

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except CloudinaryError as exc:
            raise_media_storage_validation(exc)
        except (DjangoValidationError, IntegrityError) as exc:
            raise_drf_validation(exc)


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

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except CloudinaryError as exc:
            raise_media_storage_validation(exc)

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except CloudinaryError as exc:
            raise_media_storage_validation(exc)


class AdminServiceSerializer(serializers.ModelSerializer):
    category_detail = ServiceCategorySerializer(source="category", read_only=True)
    cover_image = serializers.ImageField(required=False, allow_empty_file=False, validators=[validate_uploaded_image])
    landing_thumbnail = serializers.ImageField(required=False, allow_empty_file=False, validators=[validate_uploaded_image])
    popup_cover_image = serializers.ImageField(required=False, allow_empty_file=False, validators=[validate_uploaded_image])
    popup_content_image = serializers.ImageField(required=False, allow_empty_file=False, validators=[validate_uploaded_image])
    list_image = serializers.ImageField(required=False, allow_empty_file=False, validators=[validate_uploaded_image])
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
            "landing_group",
            "base_price",
            "selling_price",
            "effective_price",
            "advance_payment_type",
            "advance_payment_value",
            "advance_amount",
            "training_fee",
            "training_fee_per_unit",
            "estimated_duration_minutes",
            "cover_image",
            "landing_thumbnail",
            "popup_cover_image",
            "popup_content_image",
            "list_image",
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

    def validate_landing_thumbnail(self, value):
        return validate_uploaded_image(value)

    def validate_popup_cover_image(self, value):
        return validate_uploaded_image(value)

    def validate_popup_content_image(self, value):
        return validate_uploaded_image(value)

    def validate_list_image(self, value):
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
        training_fee = attrs.get("training_fee", getattr(instance, "training_fee", Decimal("0.00")))
        if training_fee < Decimal("0.00"):
            raise serializers.ValidationError({"training_fee": "Training fee cannot be negative."})
        if advance_type == AdvancePaymentType.PERCENTAGE and advance_value > Decimal("100.00"):
            raise serializers.ValidationError({"advance_payment_value": "Advance percentage cannot exceed 100."})
        if advance_type == AdvancePaymentType.FIXED and effective_price is not None and advance_value > effective_price:
            raise serializers.ValidationError({"advance_payment_value": "Advance amount cannot exceed service price."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        validated_data = self._with_synced_advance(validated_data)
        try:
            return super().create(validated_data)
        except CloudinaryError as exc:
            raise_media_storage_validation(exc)
        except (DjangoValidationError, IntegrityError) as exc:
            raise_drf_validation(exc)

    @transaction.atomic
    def update(self, instance, validated_data):
        validated_data = self._with_synced_advance(validated_data, instance=instance)
        try:
            return super().update(instance, validated_data)
        except CloudinaryError as exc:
            raise_media_storage_validation(exc)
        except (DjangoValidationError, IntegrityError) as exc:
            raise_drf_validation(exc)

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


class PackageItemSerializer(serializers.ModelSerializer):
    service_detail = ServiceListSerializer(source="service", read_only=True)

    class Meta:
        model = PackageItem
        fields = ("id", "service", "service_detail", "quantity", "display_order")
        read_only_fields = ("id", "service_detail")

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError("Quantity must be at least 1.")
        return value


class AdminPackageSerializer(serializers.ModelSerializer):
    items = PackageItemSerializer(many=True)

    class Meta:
        model = Package
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "bundle_price",
            "valid_from",
            "valid_until",
            "maximum_usage_limit",
            "is_active",
            "items",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        instance = self.instance
        valid_from = attrs.get("valid_from", getattr(instance, "valid_from", None))
        valid_until = attrs.get("valid_until", getattr(instance, "valid_until", None))
        if valid_from and valid_until and valid_from > valid_until:
            raise serializers.ValidationError({"valid_until": "Validity end date must be on or after the start date."})
        if (self.instance is None or "items" in attrs) and not attrs.get("items"):
            raise serializers.ValidationError({"items": "At least one service is required."})
        items = attrs.get("items")
        if items:
            service_ids = [item["service"].id for item in items]
            if len(service_ids) != len(set(service_ids)):
                raise serializers.ValidationError({"items": "Each service may appear only once per package."})
        return attrs

    def validate_bundle_price(self, value):
        if value < Decimal("0.00"):
            raise serializers.ValidationError("Bundle price cannot be negative.")
        return value

    def validate_maximum_usage_limit(self, value):
        if value < 1:
            raise serializers.ValidationError("Maximum usage limit must be at least 1.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        items = validated_data.pop("items")
        package = Package.objects.create(**validated_data)
        self._replace_items(package, items)
        return package

    @transaction.atomic
    def update(self, instance, validated_data):
        items = validated_data.pop("items", None)
        package = super().update(instance, validated_data)
        if items is not None:
            if not items:
                raise serializers.ValidationError({"items": "At least one service is required."})
            package.items.all().delete()
            self._replace_items(package, items)
        return package

    @staticmethod
    def _replace_items(package, items):
        for item in items:
            PackageItem.objects.create(package=package, **item)
