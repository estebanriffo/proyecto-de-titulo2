from io import StringIO
from unittest.mock import patch

from allauth.account.models import EmailAddress
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.management.commands.create_demo_users import DEMO_ACCOUNTS
from accounts.models import User


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class DemoUsersTests(TestCase):
    password = "Clave-ficticia-para-pruebas-2026"

    def create_accounts(self):
        output = StringIO()
        with patch(
            "accounts.management.commands.create_demo_users.getpass", return_value=self.password
        ):
            call_command("create_demo_users", stdout=output)
        return output.getvalue()

    def test_crea_cuatro_cuentas_ficticias_verificadas_con_roles(self):
        output = self.create_accounts()
        self.assertNotIn(self.password, output)
        self.assertEqual(User.objects.count(), 4)
        for email, role in DEMO_ACCOUNTS:
            with self.subTest(email=email):
                user = User.objects.get(email=email)
                self.assertTrue(user.check_password(self.password))
                self.assertFalse(user.is_staff)
                self.assertFalse(user.is_superuser)
                self.assertEqual(list(user.groups.values_list("name", flat=True)), [role] if role else [])
                self.assertTrue(EmailAddress.objects.get(user=user, primary=True).verified)
                response = self.client.post(
                    reverse("account_login"), {"login": email, "password": self.password}
                )
                destination = "accounts:authorized" if role else "accounts:pending"
                self.assertRedirects(response, reverse(destination))
                self.client.logout()

    def test_repetir_comando_conserva_cuentas_existentes(self):
        self.create_accounts()
        user = User.objects.get(email=DEMO_ACCOUNTS[0][0])
        password_hash = user.password
        user.groups.clear()
        with patch("accounts.management.commands.create_demo_users.getpass") as prompt:
            call_command("create_demo_users", stdout=StringIO())
        prompt.assert_not_called()
        user.refresh_from_db()
        self.assertEqual(user.password, password_hash)
        self.assertFalse(user.groups.exists())

    @override_settings(DEBUG=False)
    def test_solo_funciona_en_desarrollo(self):
        with self.assertRaisesMessage(CommandError, "DEBUG=True"):
            self.create_accounts()
        self.assertFalse(User.objects.exists())

    def test_rechaza_contrasena_invalida_sin_crear_cuentas(self):
        with patch("accounts.management.commands.create_demo_users.getpass", return_value="123"):
            with self.assertRaises(CommandError):
                call_command("create_demo_users", stdout=StringIO())
        self.assertFalse(User.objects.exists())

    def test_rechaza_confirmacion_distinta(self):
        with patch(
            "accounts.management.commands.create_demo_users.getpass",
            side_effect=[self.password, "distinta"],
        ):
            with self.assertRaisesMessage(CommandError, "coincidir"):
                call_command("create_demo_users", stdout=StringIO())
        self.assertFalse(User.objects.exists())
