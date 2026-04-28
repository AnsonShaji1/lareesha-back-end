from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from rest_framework_simplejwt.tokens import RefreshToken


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Custom adapter for handling social account authentication"""
    
    def pre_social_login(self, request, sociallogin):
        """Called when a user is about to be signed in, but not necessarily logged in yet."""
        # User is already signed in, so this is a connect
        if request.user.is_authenticated:
            sociallogin.connect(request, request.user)
    
    def save_user(self, request, sociallogin, form=None):
        """Save user after social login"""
        user = super().save_user(request, sociallogin, form)
        return user
