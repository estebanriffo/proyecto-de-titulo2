from accounts.access import can_invite, can_manage_accounts, get_educational_roles, get_roles

from .models import Activity


def is_student(user):
    return (
        user.is_authenticated
        and user.is_active
        and get_educational_roles(get_roles(user)) == {"estudiante"}
    )


def can_publish(user):
    return can_invite(user)


def visible_activities(user):
    activities = Activity.objects.all()
    if can_manage_accounts(user):
        return activities
    if can_publish(user):
        return activities.filter(owner=user)
    if is_student(user):
        return activities.filter(students=user, is_active=True)
    return activities.none()
