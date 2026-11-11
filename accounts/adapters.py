from urllib.parse import quote

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from django.conf import settings
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.views.decorators.debug import sensitive_variables

from .access import get_landing_url
from .managers import UserManager


class PasswordResetDeliveryError(Exception):
    pass


class AccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        return get_landing_url(request.user)

    def clean_email(self, email):
        return super().clean_email(UserManager.normalize_email(email))

    def get_email_confirmation_url(self, request, emailconfirmation):
        path = reverse("account_confirm_email", args=[emailconfirmation.key])
        return settings.SITE_URL + path

    @sensitive_variables()
    def get_reset_password_from_key_url(self, key):
        path = reverse(
            "account_reset_password_from_key", kwargs={"uidb36": "UID", "key": "KEY"}
        )
        return settings.SITE_URL + path.replace("UID-KEY", quote(key, safe=""))

    @sensitive_variables()
    def send_password_reset_mail(self, user, email, context):
        message = self.render_mail("account/email/password_reset_key", email, context)
        if message.send() != 1:
            raise PasswordResetDeliveryError

    def confirm_invited_email(self, invitation, user):
        if not invitation.is_available or user.email != invitation.email:
            raise ValidationError("La invitación ya no está disponible.")
        return EmailAddress.objects.create(
            user=user,
            email=invitation.email,
            primary=True,
            verified=True,
        )
