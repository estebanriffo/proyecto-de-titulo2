from smtplib import SMTPException

from allauth.account.decorators import verified_email_required
from allauth.account.views import PasswordResetView as AllauthPasswordResetView
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_http_methods, require_safe

from .access import can_invite, can_manage_accounts, get_educational_roles, get_landing_url, get_roles
from .adapters import PasswordResetDeliveryError
from .forms import InvitationAcceptForm, InvitationForm
from .services import (
    InvalidInvitation,
    InvitationDeliveryError,
    accept_invitation,
    get_available_invitation,
    send_invitation,
)


@never_cache
@require_safe
def entry(request):
    if not request.user.is_authenticated:
        return redirect("account_login")
    return redirect(get_landing_url(request.user))


@never_cache
@require_safe
@verified_email_required
def authorized(request):
    roles = get_roles(request.user)
    if not roles and not request.user.is_superuser:
        return redirect("accounts:pending")
    educational_roles = get_educational_roles(roles)
    return render(
        request,
        "accounts/authorized.html",
        {
            "roles": roles,
            "educational_role": next(iter(educational_roles)) if len(educational_roles) == 1 else None,
            "has_role_conflict": len(educational_roles) > 1,
            "can_manage_accounts": can_manage_accounts(request.user, roles),
            "can_invite": can_invite(request.user, roles),
        },
    )


@never_cache
@require_safe
@verified_email_required
def pending(request):
    if request.user.is_superuser or get_roles(request.user):
        return redirect(get_landing_url(request.user))
    return render(request, "accounts/pending.html")


@never_cache
@require_http_methods(["GET", "POST"])
@verified_email_required
def invitations(request):
    if not can_invite(request.user):
        raise PermissionDenied
    form = InvitationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            send_invitation(email=form.cleaned_data["email"], invited_by=request.user)
        except ValidationError as error:
            form.add_error("email", error)
        except InvitationDeliveryError:
            form.add_error(
                None,
                "No se pudo enviar el correo. Vuelve a intentar el envío. "
                "Si el problema continúa, contacta al administrador.",
            )
        else:
            messages.success(request, "Invitación enviada. El enlace tiene una vigencia de 48 horas.")
            return redirect("accounts:invitations")
    return render(
        request,
        "accounts/invitations.html",
        {"form": form},
    )


@never_cache
@require_http_methods(["GET", "POST"])
@sensitive_post_parameters("new_password1", "new_password2")
@sensitive_variables()
def invitation_accept(request, token):
    try:
        invitation = get_available_invitation(token)
    except InvalidInvitation:
        response = render(request, "accounts/invitation_unavailable.html", status=400)
    else:
        form = InvitationAcceptForm(
            invitation, request.POST if request.method == "POST" else None
        )
        if request.method == "POST" and form.is_valid():
            try:
                accept_invitation(
                    request=request,
                    token=token,
                    password=form.cleaned_data["new_password1"],
                )
            except InvalidInvitation:
                response = render(request, "accounts/invitation_unavailable.html", status=400)
            except ValidationError as error:
                form.add_error("new_password2", error)
                response = render(
                    request, "accounts/invitation_accept.html",
                    {"form": form, "invitation": invitation},
                )
            else:
                messages.success(
                    request,
                    "Tu cuenta fue creada. Inicia sesión con tu correo y contraseña. "
                    "Un administrador debe asignarte un rol para habilitar tu acceso.",
                )
                response = redirect("account_login")
        else:
            response = render(
                request, "accounts/invitation_accept.html",
                {"form": form, "invitation": invitation},
            )
    # Conserva el origen del POST y limita el Referer al origen, sin incluir el token.
    response.headers["Referrer-Policy"] = "strict-origin"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@method_decorator(never_cache, name="dispatch")
class PasswordResetView(AllauthPasswordResetView):
    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except (SMTPException, OSError, PasswordResetDeliveryError):
            form.add_error(
                None,
                "No se pudo enviar el correo de recuperación. Vuelve a intentar. "
                "Si el problema continúa, contacta al administrador.",
            )
            return self.form_invalid(form)
