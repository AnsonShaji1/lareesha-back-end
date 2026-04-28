"""
URL configuration for lareesha backend project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from api.views import GoogleAuthView, RegistrationView, LoginView, ForgotPasswordView, ResetPasswordConfirmView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    # Custom authentication endpoints (MUST come BEFORE include('dj_rest_auth.urls'))
    path('api/auth/login/', LoginView.as_view(), name='custom_login'),
    path('api/auth/registration/', RegistrationView.as_view(), name='custom_registration'),
    # Custom password reset endpoints
    path('api/auth/forgot-password/', ForgotPasswordView.as_view(), name='forgot_password'),
    path('api/auth/reset-password-confirm/', ResetPasswordConfirmView.as_view(), name='reset_password_confirm'),
    # Google OAuth endpoint
    path('api/auth/google/', GoogleAuthView.as_view(), name='google_auth'),
    # dj-rest-auth endpoints with allauth (comes AFTER custom endpoints)
    path('api/auth/', include('dj_rest_auth.urls')),
    path('api/accounts/', include('allauth.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)