from django.urls import reverse

EDUCATIONAL_ROLES = ("estudiante", "docente")
ROLE_NAMES = (*EDUCATIONAL_ROLES, "administrador")


def can_manage_accounts(user, roles=None):
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return "administrador" in (get_roles(user) if roles is None else roles)


def can_invite(user, roles=None):
    if not user.is_authenticated or not user.is_active:
        return False
    roles = get_roles(user) if roles is None else roles
    return can_manage_accounts(user, roles) or get_educational_roles(roles) == {"docente"}


def get_educational_roles(roles):
    return set(EDUCATIONAL_ROLES).intersection(roles)


def get_roles(user):
    return list(
        user.groups.filter(name__in=ROLE_NAMES).order_by("name").values_list("name", flat=True)
    )


def get_landing_url(user):
    if user.is_superuser:
        return reverse("admin:index")
    if get_roles(user):
        return reverse("accounts:authorized")
    return reverse("accounts:pending")
