from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    CustomTokenObtainPairView, UserRegistrationView,
    UserProfileView, ChangePasswordView,
    UserForgotPasswordRequestView, UserVerifyOTPView, UserResetPasswordView,
    UserLogoutView
)

urlpatterns = [
    # User Authentication endpoints
    path('register/', UserRegistrationView.as_view(), name='register'),
    path('login/', CustomTokenObtainPairView.as_view(), name='login'),
    path('logout/', UserLogoutView.as_view(), name='logout'),
    path('refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('profile/', UserProfileView.as_view(), name='profile'),
    path('me/', UserProfileView.as_view(), name='me'),  # Alias for profile
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),

    # User Forgot Password endpoints
    path('forgot-password/', UserForgotPasswordRequestView.as_view(), name='user-forgot-password'),
    path('verify-otp/', UserVerifyOTPView.as_view(), name='user-verify-otp'),
    path('reset-password/', UserResetPasswordView.as_view(), name='user-reset-password'),
]
