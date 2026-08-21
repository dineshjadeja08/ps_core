from rest_framework import serializers

from apps.accounts.models import CustomerProfile, User


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
