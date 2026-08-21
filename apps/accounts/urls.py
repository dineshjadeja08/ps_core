from django.urls import path

from apps.accounts.views import DevPhoneLoginView, FirebaseLoginView, LogoutView, MeView, OtpSendView, OtpVerifyView, RefreshView

urlpatterns = [
    path("firebase/", FirebaseLoginView.as_view(), name="auth-firebase"),
    path("otp/send/", OtpSendView.as_view(), name="auth-otp-send"),
    path("otp/verify/", OtpVerifyView.as_view(), name="auth-otp-verify"),
    path("dev-phone/", DevPhoneLoginView.as_view(), name="auth-dev-phone"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("refresh/", RefreshView.as_view(), name="auth-refresh"),
]
