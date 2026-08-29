from rest_framework import serializers
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field

from apps.accounts.models import CustomerProfile, CustomerSupportNote, User


class FirebaseLoginRequestSerializer(serializers.Serializer):
    id_token = serializers.CharField()


class DevPhoneLoginRequestSerializer(serializers.Serializer):
    phone_number = serializers.CharField()


class OtpSendRequestSerializer(serializers.Serializer):
    phone_number = serializers.CharField()


class OtpSendResponseSerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    request_id = serializers.CharField(allow_blank=True)


class OtpVerifyRequestSerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    otp = serializers.RegexField(regex=r"^\d{4,8}$")


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    token_type = serializers.CharField()


class CustomerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerProfile
        fields = ("id", "display_name", "alternate_phone")


class UserSerializer(serializers.ModelSerializer):
    customer_profile = CustomerProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "phone_number",
            "email",
            "first_name",
            "last_name",
            "role",
            "is_verified",
            "customer_profile",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class UserProfileUpdateSerializer(serializers.Serializer):
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    display_name = serializers.CharField(required=False, allow_blank=True, max_length=255)
    alternate_phone = serializers.CharField(required=False, allow_blank=True, max_length=16)

    def update(self, instance, validated_data):
        profile_data = {
            key: validated_data.pop(key)
            for key in ("display_name", "alternate_phone")
            if key in validated_data
        }

        if "email" in validated_data and validated_data["email"] == "":
            validated_data["email"] = None

        for field, value in validated_data.items():
            setattr(instance, field, value)

        instance.save(update_fields=[*validated_data.keys(), "updated_at"])

        if profile_data:
            profile, _ = CustomerProfile.objects.get_or_create(user=instance)
            for field, value in profile_data.items():
                setattr(profile, field, value)
            profile.save(update_fields=[*profile_data.keys(), "updated_at"])

        return instance


class AuthLoginResponseSerializer(serializers.Serializer):
    user = UserSerializer()
    tokens = TokenPairSerializer()
    created = serializers.BooleanField()


class CustomerSupportNoteSerializer(serializers.ModelSerializer):
    created_by_phone = serializers.CharField(source="created_by.phone_number", read_only=True)

    class Meta:
        model = CustomerSupportNote
        fields = ("id", "customer", "note", "created_by", "created_by_phone", "created_at", "updated_at")
        read_only_fields = ("id", "customer", "created_by", "created_by_phone", "created_at", "updated_at")


class AdminCustomerSerializer(UserSerializer):
    total_bookings = serializers.IntegerField(read_only=True)
    total_amount_spent = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    last_booking_at = serializers.DateTimeField(read_only=True)

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + (
            "is_active",
            "total_bookings",
            "total_amount_spent",
            "last_booking_at",
        )


class AdminCustomerHistorySerializer(UserSerializer):
    addresses = serializers.SerializerMethodField()
    leads = serializers.SerializerMethodField()
    bookings = serializers.SerializerMethodField()
    payments = serializers.SerializerMethodField()
    notifications = serializers.SerializerMethodField()
    reviews = serializers.SerializerMethodField()
    support_notes = CustomerSupportNoteSerializer(many=True, read_only=True)

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + (
            "is_active",
            "addresses",
            "leads",
            "bookings",
            "payments",
            "notifications",
            "reviews",
            "support_notes",
        )

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_addresses(self, obj):
        return [
            {
                "id": str(address.id),
                "label": address.label,
                "recipient_name": address.recipient_name,
                "city": address.city,
                "postal_code": address.postal_code,
                "is_default": address.is_default,
                "is_active": address.is_active,
            }
            for address in obj.addresses.all()[:20]
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_leads(self, obj):
        from apps.operations.models import Lead

        return [
            {
                "id": str(lead.id),
                "customer_name": lead.customer_name,
                "primary_mobile": lead.primary_mobile,
                "status": lead.status,
                "source": lead.source,
                "created_at": lead.created_at,
            }
            for lead in Lead.objects.filter(primary_mobile=obj.phone_number).order_by("-created_at")[:20]
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_bookings(self, obj):
        return [
            {
                "id": str(booking.id),
                "booking_number": booking.booking_number,
                "service_date": booking.service_date,
                "booking_status": booking.booking_status,
                "payment_status": booking.payment_status,
                "total_amount": booking.total_amount,
                "created_at": booking.created_at,
            }
            for booking in obj.bookings.all()[:20]
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_payments(self, obj):
        return [
            {
                "id": str(payment.id),
                "booking": str(payment.booking_id),
                "amount": payment.amount,
                "payment_type": payment.payment_type,
                "status": payment.status,
                "paid_at": payment.paid_at,
            }
            for booking in obj.bookings.all()[:20]
            for payment in booking.payments.all()[:10]
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_notifications(self, obj):
        return [
            {
                "id": str(notification.id),
                "event": notification.event,
                "channel": notification.channel,
                "status": notification.status,
                "created_at": notification.created_at,
                "sent_at": notification.sent_at,
            }
            for notification in obj.notifications.all()[:20]
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_reviews(self, obj):
        return [
            {
                "id": str(review.id),
                "rating": review.rating,
                "is_visible": review.is_visible,
                "created_at": review.created_at,
            }
            for review in obj.reviews.all()[:20]
        ]
