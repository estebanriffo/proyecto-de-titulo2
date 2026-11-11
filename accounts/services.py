import hashlib
import secrets
from datetime import timedelta
from smtplib import SMTPException

from allauth.account.adapter import get_adapter
from allauth.account.models import EmailAddress
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from .access import can_invite
from .managers import UserManager
from .models import Invitation, User


class InvitationDeliveryError(Exception):
    pass


class InvalidInvitation(Exception):
    pass


@sensitive_variables()
def send_invitation(*, email, invited_by):
    if not can_invite(invited_by):
        raise PermissionDenied
    email = UserManager.normalize_email(email)
    validate_email(email)
    if len(email) > Invitation._meta.get_field("email").max_length:
        raise ValidationError("El correo electrónico es demasiado largo.")

    try:
        with transaction.atomic():
            token = secrets.token_urlsafe(32)
            sent_at = timezone.now()
            values = {
                "token_digest": hashlib.sha256(token.encode()).hexdigest(),
                "invited_by": invited_by,
                "sent_at": sent_at,
                "expires_at": sent_at + timedelta(hours=48),
            }
            invitation, _ = Invitation.objects.select_for_update().get_or_create(
                email=email, defaults=values
            )
            if (
                User.objects.filter(email__iexact=email).exists()
                or EmailAddress.objects.filter(email__iexact=email).exists()
            ):
                raise ValidationError(
                    "Ya existe una cuenta con ese correo. Indica a la persona que inicie "
                    "sesión o recupere su contraseña.",
                    code="account_exists",
                )
            if invitation.accepted_at is not None:
                raise ValidationError(
                    "Esta invitación ya fue aceptada. La persona puede iniciar sesión "
                    "o recuperar su contraseña.",
                    code="invitation_accepted",
                )
            # La hora se toma tras obtener el bloqueo, también en un reenvío concurrente.
            invitation.sent_at = timezone.now()
            invitation.expires_at = invitation.sent_at + timedelta(hours=48)
            invitation.token_digest = values["token_digest"]
            invitation.invited_by = invited_by
            invitation.save()

            path = reverse("accounts:invitation_accept", args=[token])
            invitation_url = settings.SITE_URL + path
            body = render_to_string(
                "accounts/email/invitation.txt", {"invitation_url": invitation_url}
            )
            try:
                delivered = send_mail(
                    "Invitación a Aprendo a mi Ritmo",
                    body,
                    settings.DEFAULT_FROM_EMAIL,
                    [email],
                    fail_silently=False,
                )
            except (SMTPException, OSError):
                raise InvitationDeliveryError from None
            if delivered != 1:
                raise InvitationDeliveryError
            return invitation
    except IntegrityError:
        raise ValidationError(
            "No se pudo guardar la invitación. Vuelve a intentar el envío.",
            code="invitation_conflict",
        ) from None


@sensitive_variables()
def get_available_invitation(token, *, for_update=False):
    invitations = Invitation.objects.all()
    if for_update:
        invitations = invitations.select_for_update()
    digest = hashlib.sha256(token.encode()).hexdigest()
    invitation = invitations.filter(token_digest=digest).first()
    if invitation is None or not invitation.is_available:
        raise InvalidInvitation
    if (
        User.objects.filter(email__iexact=invitation.email).exists()
        or EmailAddress.objects.filter(email__iexact=invitation.email).exists()
    ):
        raise InvalidInvitation
    return invitation


@sensitive_variables()
def accept_invitation(*, request, token, password):
    try:
        with transaction.atomic():
            invitation = get_available_invitation(token, for_update=True)
            adapter = get_adapter(request)
            adapter.clean_password(password, user=User(email=invitation.email))
            user = User.objects.create_user(invitation.email, password)
            # La verificación se concede solo al correo obtenido del registro bloqueado.
            try:
                adapter.confirm_invited_email(invitation, user)
            except ValidationError:
                raise InvalidInvitation from None
            accepted_at = timezone.now()
            if accepted_at >= invitation.expires_at:
                raise InvalidInvitation
            invitation.accepted_at = accepted_at
            invitation.accepted_user = user
            invitation.save(update_fields=["accepted_at", "accepted_user"])
            return user
    except IntegrityError:
        # Una cuenta creada por otra transacción provoca la reversión del alta completa.
        raise InvalidInvitation from None
