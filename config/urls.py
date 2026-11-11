from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from accounts.views import entry

urlpatterns = [
    path("", entry, name="home"),
    path(
        "admin/login/",
        RedirectView.as_view(pattern_name="account_login", query_string=True),
    ),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("accounts/", include("allauth.urls")),
]
