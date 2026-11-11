from django.urls import reverse

ROLE_NAMES = ("estudiante", "docente", "administrador")


def can_manage_accounts(user):
    return user.is_authenticated and user.is_active and (
        user.is_superuser or user.groups.filter(name="administrador").exists()
    )


def can_invite(user):
    return user.is_authenticated and user.is_active and (
        user.is_superuser
        or user.groups.filter(name__in=("docente", "administrador")).exists()
    )


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
