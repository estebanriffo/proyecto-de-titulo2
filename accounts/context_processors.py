from django.conf import settings
from django.utils.crypto import salted_hmac
from django.urls import reverse

from .access import can_invite, can_manage_accounts, get_educational_roles, get_roles


def email_delivery(request):
    return {
        "email_to_console": settings.DEBUG
        and settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend",
    }


def personalization(request):
    identity = f"{request.user.pk}:{request.session.session_key or 'visitor'}"
    return {
        "personalization_scope": salted_hmac("aamr.personalization", identity).hexdigest()[:24]
    }


def role_navigation(request):
    if not request.user.is_authenticated or not request.user.is_active:
        return {}
    roles = get_roles(request.user)
    educational_roles = get_educational_roles(roles)
    educational_role = next(iter(educational_roles)) if len(educational_roles) == 1 else None
    home_functions = {
        "estudiante": [
            {
                "title": "Actividades",
                "description": "Encuentra tus actividades y practica paso a paso.",
                "action": "Ver actividades",
                "url": reverse("activities:list"),
            },
            {
                "title": "Mi progreso",
                "description": "Revisa tus avances y las actividades que hayas realizado.",
                "action": "Ver mi progreso",
            },
        ],
        "docente": [
            {
                "title": "Gestionar actividades",
                "description": "Prepara y organiza las actividades para tus estudiantes.",
                "action": "Gestionar actividades",
                "url": reverse("activities:manage"),
            },
            {
                "title": "Revisar progreso de estudiantes",
                "description": "Consulta los avances de tus estudiantes para acompañar su aprendizaje.",
                "action": "Revisar progreso",
            },
        ],
    }

    return {
        "roles": roles,
        "educational_role": educational_role,
        "home_functions": home_functions.get(educational_role, []),
        "has_role_conflict": len(educational_roles) > 1,
        "can_manage_accounts": can_manage_accounts(request.user, roles),
        "can_invite": can_invite(request.user, roles),
    }
