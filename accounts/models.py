from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from .managers import UserManager


class User(AbstractUser):
    username = None
    email = models.EmailField("correo electrónico", unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(
                Lower("email"), name="accounts_user_email_ci_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(email__regex=r"^\S(?:.*\S)?$"),
                name="accounts_user_email_no_outer_whitespace",
            ),
        ]

    def save(self, *args, **kwargs):
        self.email = UserManager.normalize_email(self.email)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email


class Invitation(models.Model):
    email = models.EmailField("correo electrónico", unique=True)
    token_digest = models.CharField(max_length=64, unique=True, editable=False)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sent_invitations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accepted_invitations",
    )

    class Meta:
        verbose_name = "invitación"
        verbose_name_plural = "invitaciones"
        constraints = [
            models.UniqueConstraint(
                Lower("email"), name="accounts_invitation_email_ci_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(email__regex=r"^\S(?:.*\S)?$"),
                name="accounts_invitation_email_no_outer_whitespace",
            ),
        ]

    def save(self, *args, **kwargs):
        self.email = UserManager.normalize_email(self.email)
        super().save(*args, **kwargs)

    @property
    def is_available(self):
        return self.accepted_at is None and timezone.now() < self.expires_at

    @property
    def status(self):
        if self.accepted_at is not None:
            return "aceptada"
        return "pendiente" if self.is_available else "vencida"

    def __str__(self):
        return self.email
