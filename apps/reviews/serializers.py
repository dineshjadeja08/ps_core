from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.catalogue.models import Service
from apps.reviews.models import Review
from apps.reviews.services import create_review


class ReviewCreateSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField()

    def create(self, validated_data):
        return create_review(
            booking_id=self.context["booking_id"],
            customer=self.context["request"].user,
            rating=validated_data["rating"],
            comment=validated_data["comment"],
        )


class ReviewSerializer(serializers.ModelSerializer):
    customer = serializers.SerializerMethodField()
    technician = serializers.SerializerMethodField()
    is_booking_review = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = (
            "id",
            "booking",
            "customer",
            "reviewer_name",
            "is_booking_review",
            "technician",
            "rating",
            "comment",
            "is_visible",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_customer(self, obj):
        if obj.customer_id is None:
            return {"name": obj.reviewer_name}
        return {
            "id": str(obj.customer_id),
            "phone_number": obj.customer.phone_number,
            "name": obj.reviewer_name or " ".join(filter(None, [obj.customer.first_name, obj.customer.last_name])),
        }

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_is_booking_review(self, obj):
        return obj.booking_id is not None

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_technician(self, obj):
        if obj.technician_id is None:
            return None
        return {
            "id": str(obj.technician_id),
            "phone_number": obj.technician.phone_number,
        }


class AdminReviewSerializer(ReviewSerializer):
    booking_number = serializers.CharField(source="booking.booking_number", read_only=True, default="")
    service = serializers.PrimaryKeyRelatedField(queryset=Service.objects.all(), required=False)
    service_name = serializers.SerializerMethodField()

    class Meta(ReviewSerializer.Meta):
        fields = ReviewSerializer.Meta.fields + ("booking_number", "service", "service_name")
        read_only_fields = ("id", "booking", "customer", "technician", "is_booking_review", "booking_number", "service_name", "created_at", "updated_at")

    @extend_schema_field(OpenApiTypes.STR)
    def get_service_name(self, obj):
        return obj.booking.service.name if obj.booking_id else obj.service.name if obj.service_id else ""

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.booking_id:
            data["service"] = str(instance.booking.service_id)
        return data

    def validate(self, attrs):
        instance = self.instance
        if instance and instance.booking_id:
            if "service" in attrs and attrs["service"].id != instance.booking.service_id:
                raise serializers.ValidationError({"service": "A booking review must stay with its booked service."})
        else:
            errors = {}
            if not attrs.get("service", getattr(instance, "service", None)):
                errors["service"] = "Select a service for this review."
            if not attrs.get("reviewer_name", getattr(instance, "reviewer_name", "")).strip():
                errors["reviewer_name"] = "Enter the reviewer's name."
            if not attrs.get("comment", getattr(instance, "comment", "")).strip():
                errors["comment"] = "Enter the review text."
            if errors:
                raise serializers.ValidationError(errors)
        return attrs
