from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.entry, name="entry"),
    path("home/", views.authorized, name="authorized"),
    path("pending/", views.pending, name="pending"),
    path("password/reset/", views.PasswordResetView.as_view(), name="password_reset"),
    path("invitations/", views.invitations, name="invitations"),
    path("invitations/accept/<str:token>/", views.invitation_accept, name="invitation_accept"),
]
