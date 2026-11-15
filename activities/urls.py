from django.urls import path

from . import views

app_name = "activities"

urlpatterns = [
    path("", views.activity_list, name="list"),
    path("manage/", views.manage, name="manage"),
    path("upload/", views.upload, name="upload"),
    path("<uuid:pk>/", views.play, name="play"),
    path("<uuid:pk>/cover/", views.cover, name="cover"),
    path("files/<str:token>/<path:filename>", views.asset, name="asset"),
]
