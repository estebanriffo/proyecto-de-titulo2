from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from accounts.models import User


class UserManagerTests(SimpleTestCase):
    def test_normaliza_el_correo_sin_alterar_puntos_o_sufijos(self):
        self.assertEqual(
            User.objects.normalize_email("  Nombre.Apellido+PIE@Colegio.EXAMPLE  "),
            "nombre.apellido+pie@colegio.example",
        )

    def test_crea_usuario_con_correo_y_contrasena_cifrada(self):
        with patch.object(User, "save"):
            user = User.objects.create_user(
                "  ESTUDIANTE@Colegio.example ", "Clave-ficticia-para-pruebas-2026"
            )
        self.assertEqual(user.email, "estudiante@colegio.example")
        self.assertTrue(user.check_password("Clave-ficticia-para-pruebas-2026"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_ausencia_de_contrasena_genera_una_contrasena_inutilizable(self):
        with patch.object(User, "save"):
            user = User.objects.create_user("estudiante@colegio.example")
        self.assertFalse(user.has_usable_password())

    def test_rechaza_correo_vacio(self):
        for email in (None, "", "   "):
            with self.subTest(email=email), self.assertRaises(ValueError):
                User.objects.create_user(email)

    def test_rechaza_correo_invalido(self):
        with self.assertRaises(ValidationError):
            User.objects.create_user("correo-invalido")

    def test_superusuario_recibe_indicadores_administrativos(self):
        with patch.object(User, "save"):
            user = User.objects.create_superuser("admin@colegio.example")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_rechaza_superusuario_con_indicadores_inconsistentes(self):
        for flag in ("is_staff", "is_superuser"):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                User.objects.create_superuser("admin@colegio.example", **{flag: False})
