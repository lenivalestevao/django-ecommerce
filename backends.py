from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    """Lets customers log in with their email address (case-insensitive)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None

        User = get_user_model()

        for user in User.objects.filter(email__iexact=username.strip()):
            if user.check_password(password) and self.user_can_authenticate(user):
                return user

        return None
