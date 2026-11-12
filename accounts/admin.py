from django import forms
from django.contrib import admin
from django.contrib.auth.models import Group

from .access import ROLE_NAMES, can_manage_accounts, get_educational_roles
from .models import User


class UserRolesForm(forms.ModelForm):
    def clean_groups(self):
        groups = self.cleaned_data["groups"]
        if len(get_educational_roles(group.name for group in groups)) > 1:
            raise forms.ValidationError("Selecciona solo uno de los roles: estudiante o docente.")
        return groups


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    # Django Admin actualiza la fila del usuario antes de guardar sus grupos
    # dentro de la misma transacción, lo que serializa las ediciones en PostgreSQL.
    form = UserRolesForm
    list_display = ("email", "is_active")
    list_filter = ("is_active", "groups")
    search_fields = ("email",)
    ordering = ("email",)
    fields = ("email", "is_active", "groups", "date_joined", "last_login")
    readonly_fields = ("email", "date_joined", "last_login")
    filter_horizontal = ("groups",)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if not request.user.is_superuser:
            queryset = queryset.filter(is_superuser=False)
        return queryset

    def has_view_permission(self, request, obj=None):
        return can_manage_accounts(request.user) and super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return can_manage_accounts(request.user) and super().has_change_permission(request, obj)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "groups":
            kwargs["queryset"] = Group.objects.filter(name__in=ROLE_NAMES)
        return super().formfield_for_manytomany(db_field, request, **kwargs)


admin.site.unregister(Group)
