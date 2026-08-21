from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

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

    class Meta:
        model = Review
        fields = (
            "id",
            "booking",
            "customer",
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
        return {
            "id": str(obj.customer_id),
            "phone_number": obj.customer.phone_number,
        }

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_technician(self, obj):
        if obj.technician_id is None:
            return None
        return {
            "id": str(obj.technician_id),
            "phone_number": obj.technician.phone_number,
        }
