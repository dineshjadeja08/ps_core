from drf_spectacular.utils import OpenApiExample, extend_schema
from django.db.models import Count, Max, Q, Sum
from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.serializers import (
    AdminCustomerHistorySerializer,
    AdminCustomerSerializer,
    AdminStaffSerializer,
    AdminStaffUpdateSerializer,
    CustomerSupportNoteSerializer,
    DevPhoneLoginRequestSerializer,
    FirebaseLoginRequestSerializer,
    AuthLoginResponseSerializer,
    OtpSendRequestSerializer,
    OtpSendResponseSerializer,
    OtpVerifyRequestSerializer,
    PasswordLoginRequestSerializer,
    PasswordSignupRequestSerializer,
    StaffGroupSerializer,
    UserSerializer,
    UserProfileUpdateSerializer,
)
from apps.accounts.models import CustomerSupportNote, User, UserRole
from apps.accounts.permissions import IsAdminRole, IsSuperAdminRole
from apps.audit.models import AuditAction
from apps.audit.services import audit_event
from apps.accounts.services import (
    authenticate_dev_phone,
    authenticate_with_firebase,
    authenticate_with_otp,
    authenticate_with_password,
    register_with_password,
    send_login_otp,
)
from django.conf import settings


class FirebaseLoginView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_scope = "auth"

    @extend_schema(
        summary="Authenticate with Firebase phone token",
        description=(
            "Verifies a Firebase ID token server-side, extracts the verified phone number, "
            "creates or retrieves the Purple Squad user, and returns backend JWT credentials."
        ),
        request=FirebaseLoginRequestSerializer,
        responses={status.HTTP_200_OK: AuthLoginResponseSerializer},
        examples=[
            OpenApiExample(
                "Login request",
                value={"id_token": "firebase-id-token"},
                request_only=True,
            ),
            OpenApiExample(
                "Login response",
                value={
                    "user": {
                        "id": "67d9bd9d-31af-4c75-b443-04377885242e",
                        "phone_number": "+919876543210",
                        "email": None,
                        "first_name": "",
                        "last_name": "",
                        "role": "CUSTOMER",
                        "is_verified": True,
                        "customer_profile": {
                            "id": "406f0389-df33-4a09-aed7-1fcb66f85321",
                            "display_name": "",
                            "alternate_phone": "",
                        },
                        "created_at": "2026-08-18T12:00:00+05:30",
                        "updated_at": "2026-08-18T12:00:00+05:30",
                    },
                    "tokens": {
                        "access": "jwt-access-token",
                        "refresh": "jwt-refresh-token",
                        "token_type": "Bearer",
                    },
                    "created": True,
                },
                response_only=True,
                status_codes=["200"],
            ),
        ],
    )
    def post(self, request):
        serializer = FirebaseLoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = authenticate_with_firebase(serializer.validated_data["id_token"])
        return Response(
            {
                "user": UserSerializer(result["user"]).data,
                "tokens": result["tokens"],
                "created": result["created"],
            }
        )


class DevPhoneLoginView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_scope = "auth"

    @extend_schema(
        summary="Development phone login",
        description="Debug-only temporary login for local development while Firebase Phone Auth is unavailable.",
        request=DevPhoneLoginRequestSerializer,
        responses={status.HTTP_200_OK: AuthLoginResponseSerializer},
    )
    def post(self, request):
        if not settings.DEBUG or not settings.DEV_PHONE_LOGIN_ENABLED:
            return Response(
                {"error": {"code": "DEV_LOGIN_DISABLED", "message": "Development phone login is disabled.", "details": {}}},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = DevPhoneLoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone_number = serializer.validated_data["phone_number"]
        if phone_number not in settings.DEV_PHONE_LOGIN_ALLOWED_NUMBERS:
            return Response(
                {"error": {"code": "DEV_LOGIN_NOT_ALLOWED", "message": "This phone number is not allowed for development login.", "details": {}}},
                status=status.HTTP_403_FORBIDDEN,
            )

        result = authenticate_dev_phone(phone_number)
        return Response(
            {
                "user": UserSerializer(result["user"]).data,
                "tokens": result["tokens"],
                "created": result["created"],
            }
        )


class PasswordSignupView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_scope = "auth"

    @extend_schema(
        summary="Create account with phone and password",
        description="Temporary phone-password customer account creation while OTP delivery is being configured.",
        request=PasswordSignupRequestSerializer,
        responses={status.HTTP_201_CREATED: AuthLoginResponseSerializer},
    )
    def post(self, request):
        serializer = PasswordSignupRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = register_with_password(**serializer.validated_data)
        return Response(
            {
                "user": UserSerializer(result["user"]).data,
                "tokens": result["tokens"],
                "created": result["created"],
            },
            status=status.HTTP_201_CREATED,
        )


class PasswordLoginView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_scope = "auth"

    @extend_schema(
        summary="Login with phone and password",
        description="Temporary phone-password customer login while OTP delivery is being configured.",
        request=PasswordLoginRequestSerializer,
        responses={status.HTTP_200_OK: AuthLoginResponseSerializer},
    )
    def post(self, request):
        serializer = PasswordLoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = authenticate_with_password(**serializer.validated_data)
        return Response(
            {
                "user": UserSerializer(result["user"]).data,
                "tokens": result["tokens"],
                "created": result["created"],
            }
        )


class OtpSendView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_scope = "auth"

    @extend_schema(
        summary="Send phone OTP",
        description="Sends a login OTP through the configured backend OTP provider.",
        request=OtpSendRequestSerializer,
        responses={status.HTTP_200_OK: OtpSendResponseSerializer},
    )
    def post(self, request):
        serializer = OtpSendRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = send_login_otp(serializer.validated_data["phone_number"])
        return Response(result)


class OtpVerifyView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_scope = "auth"

    @extend_schema(
        summary="Verify phone OTP",
        description="Verifies a phone OTP and returns Purple Squad JWT credentials.",
        request=OtpVerifyRequestSerializer,
        responses={status.HTTP_200_OK: AuthLoginResponseSerializer},
    )
    def post(self, request):
        serializer = OtpVerifyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = authenticate_with_otp(
            serializer.validated_data["phone_number"],
            serializer.validated_data["otp"],
        )
        return Response(
            {
                "user": UserSerializer(result["user"]).data,
                "tokens": result["tokens"],
                "created": result["created"],
            }
        )


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get current user",
        description="Returns the authenticated Purple Squad user profile.",
        responses={status.HTTP_200_OK: UserSerializer},
    )
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    @extend_schema(
        summary="Update current user profile",
        description="Updates editable customer profile fields for the authenticated user.",
        request=UserProfileUpdateSerializer,
        responses={status.HTTP_200_OK: UserSerializer},
    )
    def patch(self, request):
        serializer = UserProfileUpdateSerializer(instance=request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Logout",
        description="Blacklists the supplied refresh token. The access token naturally expires.",
        request={
            "application/json": {
                "type": "object",
                "properties": {"refresh": {"type": "string"}},
                "required": ["refresh"],
            }
        },
        responses={status.HTTP_204_NO_CONTENT: None},
        examples=[OpenApiExample("Logout request", value={"refresh": "jwt-refresh-token"}, request_only=True)],
    )
    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"error": {"code": "VALIDATION_ERROR", "message": "Refresh token is required.", "details": {}}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            RefreshToken(refresh_token).blacklist()
        except TokenError:
            return Response(
                {"error": {"code": "AUTH_INVALID_TOKEN", "message": "Invalid refresh token.", "details": {}}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class RefreshView(TokenRefreshView):
    serializer_class = TokenRefreshSerializer
    throttle_scope = "auth"

    @extend_schema(
        summary="Refresh JWT access token",
        description="Returns a new access token for a valid refresh token.",
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class AdminCustomerViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, IsAdminRole]
    lookup_field = "id"
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_serializer_class(self):
        if self.action == "retrieve":
            return AdminCustomerHistorySerializer
        return AdminCustomerSerializer

    def get_queryset(self):
        queryset = (
            User.objects.filter(role=UserRole.CUSTOMER)
            .select_related("customer_profile")
            .prefetch_related("addresses", "bookings", "bookings__payments", "notifications", "reviews", "support_notes")
            .annotate(
                total_bookings=Count("bookings", distinct=True),
                total_amount_spent=Sum("bookings__total_amount"),
                last_booking_at=Max("bookings__created_at"),
            )
            .order_by("-created_at")
        )
        search = self.request.query_params.get("search")
        if search:
            term = search.strip()
            queryset = queryset.filter(
                Q(phone_number__icontains=term) | Q(first_name__icontains=term) | Q(last_name__icontains=term)
            )
        return queryset

    @extend_schema(summary="List customers for admin", responses={status.HTTP_200_OK: AdminCustomerSerializer(many=True)})
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Get customer history for admin", responses={status.HTTP_200_OK: AdminCustomerHistorySerializer})
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        summary="Add customer support note",
        request=CustomerSupportNoteSerializer,
        responses={status.HTTP_201_CREATED: CustomerSupportNoteSerializer},
    )
    @action(detail=True, methods=["post"], url_path="support-notes")
    def add_support_note(self, request, *args, **kwargs):
        customer = self.get_object()
        serializer = CustomerSupportNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = CustomerSupportNote.objects.create(
            customer=customer,
            note=serializer.validated_data["note"],
            created_by=request.user,
        )
        audit_event(
            action=AuditAction.CUSTOMER_SUPPORT_NOTE_CREATED,
            actor=request.user,
            request=request,
            resource_type="customer",
            resource_id=customer.id,
            metadata={"note_id": str(note.id)},
        )
        return Response(CustomerSupportNoteSerializer(note).data, status=status.HTTP_201_CREATED)


class AdminStaffViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, IsSuperAdminRole]
    lookup_field = "id"
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_serializer_class(self):
        if self.action in {"partial_update", "update"}:
            return AdminStaffUpdateSerializer
        return AdminStaffSerializer

    def get_queryset(self):
        queryset = User.objects.filter(is_staff=True).prefetch_related("groups").order_by("phone_number")
        search = self.request.query_params.get("search")
        if search:
            term = search.strip()
            queryset = queryset.filter(Q(phone_number__icontains=term) | Q(first_name__icontains=term) | Q(last_name__icontains=term))
        return queryset

    @extend_schema(summary="List staff users for admin", responses={status.HTTP_200_OK: AdminStaffSerializer(many=True)})
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Get staff user for admin", responses={status.HTTP_200_OK: AdminStaffSerializer})
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(summary="Update staff user for admin", request=AdminStaffUpdateSerializer, responses={status.HTTP_200_OK: AdminStaffSerializer})
    def partial_update(self, request, *args, **kwargs):
        response = super().partial_update(request, *args, **kwargs)
        audit_event(
            action=AuditAction.STAFF_UPDATED,
            actor=request.user,
            request=request,
            resource_type="staff",
            resource_id=response.data["id"],
            metadata={"fields": list(request.data.keys())},
        )
        return response


class AdminStaffGroupViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsSuperAdminRole]
    serializer_class = StaffGroupSerializer

    @extend_schema(summary="List staff groups for admin", responses={status.HTTP_200_OK: StaffGroupSerializer(many=True)})
    def list(self, request, *args, **kwargs):
        return Response([{"id": group.id, "name": group.name} for group in Group.objects.order_by("name")])
