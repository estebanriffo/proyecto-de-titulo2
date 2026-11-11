from functools import wraps

from django.contrib.admin import AdminSite
from django.core.exceptions import PermissionDenied
from django.urls import reverse_lazy

from accounts.access import can_manage_accounts


class ProjectAdminSite(AdminSite):
    site_header = "Administración de Aprendo a mi Ritmo"
    site_title = "Aprendo a mi Ritmo"
    site_url = reverse_lazy("accounts:authorized")

    def has_permission(self, request):
        return can_manage_accounts(request.user)

    def admin_view(self, view, cacheable=False):
        protected_view = super().admin_view(view, cacheable=cacheable)

        @wraps(view)
        def check_access(request, *args, **kwargs):
            if request.user.is_authenticated and not self.has_permission(request):
                raise PermissionDenied
            return protected_view(request, *args, **kwargs)

        return check_access
