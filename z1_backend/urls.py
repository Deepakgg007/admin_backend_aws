
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    path("api/auth/", include("authentication.urls")),  # Authentication app routes
    path("api/college/", include("college.urls")),  # College app routes
    path("api/student/", include("student.urls")),  # Student app routes
    path("api/courses/", include("courses.urls")),  # Courses app routes
    path("api/company/", include("company.urls")),  # Company challenges and jobs routes
    path("api/admin/dashboard/", include("admin_dashboard.urls")),  # Admin dashboard routes
]


# Serve media and static files in development
# Note: In production, use a proper web server (nginx/apache) to serve these files
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
