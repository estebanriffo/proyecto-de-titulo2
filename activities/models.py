from uuid import uuid4

from django.conf import settings
from django.db import models


class Activity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    title = models.CharField("nombre", max_length=100)
    description = models.CharField("descripción", max_length=300)
    entrypoint = models.CharField(max_length=255)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    students = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="assigned_activities", verbose_name="alumnos"
    )
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]
        verbose_name = "actividad"
        verbose_name_plural = "actividades"

    def __str__(self):
        return self.title
