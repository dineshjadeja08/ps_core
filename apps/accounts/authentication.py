from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.accounts.models import UserRole


class MfaEnforcedJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN} and validated_token.get("mfa") is not True:
            raise AuthenticationFailed("Administrator MFA is required.", code="admin_mfa_required")
        return user
