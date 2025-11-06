from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema, OpenApiResponse
from datetime import timedelta

from .serializers import (
    UserRegistrationSerializer, UserSerializer, UserProfileUpdateSerializer,
    LoginSerializer, LoginResponseSerializer, ChangePasswordSerializer,
    ForgotPasswordRequestSerializer, VerifyOTPSerializer, ResetPasswordSerializer
)
from api.utils import StandardResponseMixin

User = get_user_model()


class CustomTokenObtainPairView(TokenObtainPairView, StandardResponseMixin):
    @extend_schema(
        tags=['Authentication - User'],
        request=LoginSerializer,
        responses={
            200: LoginResponseSerializer,
            400: OpenApiResponse(description='Invalid credentials')
        },
        summary="User Login",
        description="Login with email and password to get JWT tokens and user information including staff/superuser status"
    )
    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        remember_me = serializer.validated_data.get('remember_me', False)

        refresh = RefreshToken.for_user(user)

        # If remember_me is True, extend token lifetime
        if remember_me:
            refresh.set_exp(lifetime=timedelta(days=30))  # 30 days refresh token
            refresh.access_token.set_exp(lifetime=timedelta(days=7))  # 7 days access token

        # Create response data
        response_data = {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': UserSerializer(user).data
        }

        return self.success_response(
            data=response_data,
            message="Login successful."
        )


class UserRegistrationView(generics.CreateAPIView, StandardResponseMixin):
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]

    @extend_schema(tags=['Authentication - User'])

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return self.success_response(
            data={
                'user': UserSerializer(user).data,
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            },
            message="Registration successful.",
            status_code=status.HTTP_201_CREATED
        )


class UserProfileView(generics.RetrieveUpdateAPIView, StandardResponseMixin):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Authentication - User'])

    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return self.success_response(
            data=serializer.data,
            message="Profile retrieved successfully."
        )

    def update(self, request, *args, **kwargs):
        serializer = UserProfileUpdateSerializer(
            instance=request.user,
            data=request.data,
            partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.success_response(
            data=UserSerializer(request.user).data,
            message="Profile updated successfully."
        )


class ChangePasswordView(generics.UpdateAPIView, StandardResponseMixin):
    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Authentication - User'])

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.success_response(
            message="Password changed successfully."
        )


# Forgot Password Views for Users

class UserForgotPasswordRequestView(APIView, StandardResponseMixin):
    """Request OTP for user password reset"""
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Authentication - User - Password Reset'],
        request=ForgotPasswordRequestSerializer,
        responses={
            200: OpenApiResponse(description='OTP sent successfully'),
            400: OpenApiResponse(description='Invalid email or user not found')
        },
        summary="Request Password Reset OTP",
        description="Send OTP to registered user email for password reset"
    )
    def post(self, request):
        from api.utils import create_otp_record, send_otp_email

        serializer = ForgotPasswordRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        # Check if user exists
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return self.error_response(
                message="No user found with this email address.",
                status_code=status.HTTP_404_NOT_FOUND
            )

        # Create OTP record
        otp = create_otp_record(email, otp_type='user')

        # Send OTP email
        email_sent = send_otp_email(email, otp.otp_code, user_type='user')

        if not email_sent:
            return self.error_response(
                message="Failed to send OTP email. Please try again.",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return self.success_response(
            message=f"OTP has been sent to {email}. Please check your inbox.",
            data={"email": email}
        )


class UserVerifyOTPView(APIView, StandardResponseMixin):
    """Verify OTP for user password reset"""
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Authentication - User - Password Reset'],
        request=VerifyOTPSerializer,
        responses={
            200: OpenApiResponse(description='OTP verified successfully'),
            400: OpenApiResponse(description='Invalid or expired OTP')
        },
        summary="Verify OTP",
        description="Verify the OTP code sent to user email"
    )
    def post(self, request):
        from api.utils import verify_otp

        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        otp_code = serializer.validated_data['otp_code']

        # Verify OTP
        is_valid, message = verify_otp(email, otp_code, otp_type='user')

        if not is_valid:
            return self.error_response(message=message, status_code=status.HTTP_400_BAD_REQUEST)

        return self.success_response(
            message="OTP verified successfully. You can now reset your password.",
            data={"email": email}
        )


class UserResetPasswordView(APIView, StandardResponseMixin):
    """Reset user password with verified OTP"""
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Authentication - User - Password Reset'],
        request=ResetPasswordSerializer,
        responses={
            200: OpenApiResponse(description='Password reset successfully'),
            400: OpenApiResponse(description='Invalid OTP or user not found')
        },
        summary="Reset Password",
        description="Reset user password using verified OTP"
    )
    def post(self, request):
        from .models import OTP

        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        otp_code = serializer.validated_data['otp_code']
        new_password = serializer.validated_data['new_password']

        # Check if OTP is verified
        try:
            otp = OTP.objects.get(
                email=email,
                otp_code=otp_code,
                otp_type='user',
                is_verified=True
            )

            if otp.is_expired():
                return self.error_response(
                    message="OTP has expired. Please request a new one.",
                    status_code=status.HTTP_400_BAD_REQUEST
                )

        except OTP.DoesNotExist:
            return self.error_response(
                message="Invalid or unverified OTP. Please verify your OTP first.",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # Get user and reset password
        try:
            user = User.objects.get(email=email)
            user.set_password(new_password)
            user.save()

            # Delete used OTP
            OTP.objects.filter(email=email, otp_type='user').delete()

            return self.success_response(
                message="Password reset successfully. You can now login with your new password.",
                data={"email": email}
            )

        except User.DoesNotExist:
            return self.error_response(
                message="User not found.",
                status_code=status.HTTP_404_NOT_FOUND
            )
