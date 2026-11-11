from allauth.account.forms import LoginForm as AllauthLoginForm
from django import forms
from django.contrib.auth.forms import SetPasswordForm

from .managers import UserManager
from .models import Invitation, User


class LoginForm(AllauthLoginForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].help_text = ""

    def clean_login(self):
        return UserManager.normalize_email(super().clean_login())


class InvitationForm(forms.Form):
    email = forms.EmailField(
        label="Correo electrónico de la persona invitada",
        max_length=Invitation._meta.get_field("email").max_length,
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )

    def clean_email(self):
        return UserManager.normalize_email(self.cleaned_data["email"])


class InvitationAcceptForm(SetPasswordForm):
    def __init__(self, invitation, *args, **kwargs):
        super().__init__(User(email=invitation.email), *args, **kwargs)
