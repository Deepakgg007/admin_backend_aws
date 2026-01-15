from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import exception_handler
from rest_framework import status


class StandardResponseMixin:
    """Mixin to provide standardized API responses"""

    @staticmethod
    def success_response(data=None, message="Success", status_code=status.HTTP_200_OK, pagination=None):
        response_data = {
            "success": True,
            "message": message,
            "data": data
        }
        if pagination:
            response_data["pagination"] = pagination
        return Response(response_data, status=status_code)

    @staticmethod
    def error_response(message="Error", errors=None, status_code=status.HTTP_400_BAD_REQUEST):
        response_data = {
            "success": False,
            "message": message
        }
        if errors:
            response_data["errors"] = errors
        return Response(response_data, status=status_code)


class CustomPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'per_page'
    max_page_size = 10000  # Increased to allow fetching all topics/courses

    def get_paginated_response(self, data):
        next_url = self.get_next_link()
        prev_url = self.get_previous_link()

        return Response({
            'success': True,
            'message': 'Data retrieved successfully.',
            'data': data,
            'pagination': {
                'current_page': self.page.number,
                'total_pages': self.page.paginator.num_pages,
                'per_page': self.page_size,
                'total': self.page.paginator.count,
                'next_page_url': next_url,
                'prev_page_url': prev_url
            }
        })


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        error_message = "An error occurred"
        error_details = {}

        if hasattr(exc, 'detail'):
            if isinstance(exc.detail, dict):
                error_details = exc.detail
                error_message = "Validation error."
            elif isinstance(exc.detail, list):
                error_details = {"detail": exc.detail}
                error_message = "Validation error."
            else:
                error_message = str(exc.detail)

        if response.status_code == 404:
            error_message = "Resource not found."
        elif response.status_code == 401:
            error_message = "Authentication required."
        elif response.status_code == 403:
            error_message = "Permission denied."
        elif response.status_code == 500:
            error_message = "Internal server error."

        custom_response = {
            'success': False,
            'message': error_message
        }

        if error_details:
            custom_response['errors'] = error_details

        response.data = custom_response

    return response


# OTP and Email Utilities

import random
import string
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


def generate_otp(length=6):
    """Generate a random 6-digit OTP"""
    return ''.join(random.choices(string.digits, k=length))


def send_otp_email(email, otp_code, user_type='user'):
    """Send OTP to user's email"""
    subject = 'Z1 Solution - Password Reset OTP'

    user_type_display = 'User' if user_type == 'user' else 'College'

    message = f"""
Hello,

You have requested to reset your password for your {user_type_display} account.

Your OTP code is: {otp_code}

This OTP will expire in 10 minutes.

If you did not request this password reset, please ignore this email.

Best regards,
Z1 Solution Team
"""

    html_message = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; }}
        .content {{ background-color: #f9f9f9; padding: 30px; border-radius: 5px; margin: 20px 0; }}
        .otp-code {{ font-size: 32px; font-weight: bold; color: #4CAF50; text-align: center; padding: 20px; background-color: white; border-radius: 5px; letter-spacing: 5px; }}
        .footer {{ text-align: center; color: #777; font-size: 12px; margin-top: 20px; }}
        .warning {{ color: #ff6b6b; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Password Reset Request</h1>
        </div>
        <div class="content">
            <p>Hello,</p>
            <p>You have requested to reset your password for your <strong>{user_type_display}</strong> account.</p>
            <p>Your OTP code is:</p>
            <div class="otp-code">{otp_code}</div>
            <p class="warning">⚠️ This OTP will expire in 10 minutes.</p>
            <p>If you did not request this password reset, please ignore this email.</p>
        </div>
        <div class="footer">
            <p>Best regards,<br>Z1 Solution Team</p>
        </div>
    </div>
</body>
</html>
"""

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


def create_otp_record(email, otp_type='user'):
    """Create OTP record in database"""
    from authentication.models import OTP

    # Delete existing OTPs for this email and type
    OTP.objects.filter(email=email, otp_type=otp_type, is_verified=False).delete()

    # Generate new OTP
    otp_code = generate_otp()

    # Create OTP record with 10 minutes expiry
    otp = OTP.objects.create(
        email=email,
        otp_code=otp_code,
        otp_type=otp_type,
        expires_at=timezone.now() + timedelta(minutes=10)
    )

    return otp


def verify_otp(email, otp_code, otp_type='user'):
    """Verify OTP code"""
    from authentication.models import OTP

    try:
        otp = OTP.objects.get(
            email=email,
            otp_code=otp_code,
            otp_type=otp_type,
            is_verified=False
        )

        if otp.is_expired():
            return False, "OTP has expired. Please request a new one."

        # Mark as verified
        otp.is_verified = True
        otp.save()

        return True, "OTP verified successfully."

    except OTP.DoesNotExist:
        return False, "Invalid OTP code."
