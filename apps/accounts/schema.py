from drf_spectacular.extensions import OpenApiAuthenticationExtension


class MfaEnforcedJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.accounts.authentication.MfaEnforcedJWTAuthentication"
    name = "jwtAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT authentication. Administrator MFA is enforced when ADMIN_MFA_ENABLED is true.",
        }
