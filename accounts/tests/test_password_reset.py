import logging
import re
from datetime import timedelta
from smtplib import SMTPException
from unittest.mock import patch
from urllib.parse import urlsplit

from allauth.account.forms import default_token_generator
from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth.models import Group
from django.core import mail
from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import Invitation, User


class PasswordResetLoggingTests(SimpleTestCase):
    @override_settings(DEBUG=True)
    def test_registros_de_django_ocultan_enlace_de_recuperacion(self):
        for handler in logging.getLogger("django").handlers:
            with self.subTest(handler=handler.name):
                record = logging.LogRecord(
                    "django.request", logging.WARNING, __file__, 1,
                    "Forbidden: %s",
                    ("/accounts/password/reset/key/1-token-de-recuperacion/",), None,
                )
                handler.filter(record)
                self.assertNotIn("token-de-recuperacion", record.getMessage())
                self.assertIn("/accounts/password/reset/key/[oculto]/", record.getMessage())


@override_settings(
    SECURE_SSL_REDIRECT=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    SITE_URL="https://aprendo.example",
)
class PasswordResetTests(TestCase):
    old_password = "Clave-anterior-ficticia-2026"
    new_password = "Nueva-clave-ficticia-para-pruebas-2026"

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            "persona.apellido+pie@colegio.example", cls.old_password
        )
        EmailAddress.objects.create(
            user=cls.user, email=cls.user.email, primary=True, verified=True
        )
        cls.user.groups.add(Group.objects.get(name="docente"))

    def setUp(self):
        cache.clear()
        self.url = reverse("account_reset_password")

    def request_link(self, email=None, **extra):
        response = self.client.post(self.url, {"email": email or self.user.email}, **extra)
        self.assertRedirects(response, reverse("account_reset_password_done"))
        return response

    def open_link(self, client=None, **extra):
        client = client or self.client
        message = mail.outbox[-1]
        url = re.search(r"https://aprendo\.example/accounts/password/reset/key/[^\s]+", message.body).group(0)
        response = client.get(urlsplit(url).path, **extra)
        self.assertEqual(response.status_code, 302)
        self.assertIn("-set-password/", response.url)
        form_url = response.url
        page = client.get(form_url, **extra)
        self.assertContains(page, "Guardar nueva contraseña")
        return urlsplit(url).path, form_url, page

    def reset(self, form_url, **extra):
        return self.client.post(
            form_url,
            {"password1": self.new_password, "password2": self.new_password, **extra},
        )

    def test_entrada_desde_login_y_formulario_en_espanol(self):
        login = self.client.get(reverse("account_login"))
        self.assertContains(login, f'href="{self.url}"', count=1)
        response = self.client.get(self.url)
        self.assertContains(response, "Recuperar contraseña")
        self.assertContains(response, 'for="id_email"')
        self.assertContains(response, 'type="email"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')

    def test_respuesta_generica_para_cuenta_habilitada_deshabilitada_y_desconocida(self):
        self.request_link()
        enabled_response = self.client.get(reverse("account_reset_password_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.request_link()
        disabled_response = self.client.get(reverse("account_reset_password_done"))
        self.request_link(email="desconocida@colegio.example")
        unknown_response = self.client.get(reverse("account_reset_password_done"))
        self.assertEqual(enabled_response.content, disabled_response.content)
        self.assertEqual(enabled_response.content, unknown_response.content)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(Invitation.objects.exists())

    @override_settings(ALLOWED_HOSTS=["testserver", "ajeno.example"])
    def test_correo_normalizado_enlace_con_site_url_y_mensaje_en_espanol(self):
        self.request_link(
            email=" PERSONA.APELLIDO+PIE@COLEGIO.EXAMPLE ", HTTP_HOST="ajeno.example"
        )
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.user.email])
        self.assertIn("Recuperación de contraseña", message.subject)
        self.assertIn("https://aprendo.example/accounts/password/reset/key/", message.body)
        self.assertNotIn("ajeno.example", message.body)
        self.assertIn("Abre el siguiente enlace", message.body)

    def test_cambio_de_contrasena_conserva_roles_y_requiere_iniciar_sesion(self):
        self.request_link()
        original_url, form_url, _ = self.open_link()
        response = self.reset(
            form_url, groups="administrador", is_staff="true", is_superuser="true"
        )
        self.assertRedirects(response, reverse("account_reset_password_from_key_done"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))
        self.assertFalse(self.user.check_password(self.old_password))
        self.assertTrue(self.user.is_active)
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self.assertEqual(list(self.user.groups.values_list("name", flat=True)), ["docente"])
        self.assertNotIn("_auth_user_id", self.client.session)
        invalid = self.client.get(original_url)
        self.assertContains(invalid, "Enlace no disponible")
        self.assertNotContains(invalid, 'type="password"')
        old_login = self.client.post(
            reverse("account_login"), {"login": self.user.email, "password": self.old_password}
        )
        self.assertEqual(old_login.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        new_login = self.client.post(
            reverse("account_login"), {"login": self.user.email, "password": self.new_password}
        )
        self.assertRedirects(new_login, reverse("accounts:authorized"))

    def test_cuenta_sin_grupo_permanece_en_espera_despues_del_cambio(self):
        self.user.groups.clear()
        self.request_link()
        _, form_url, _ = self.open_link()
        self.assertEqual(self.reset(form_url).status_code, 302)
        self.user.refresh_from_db()
        self.assertFalse(self.user.groups.exists())
        response = self.client.post(
            reverse("account_login"), {"login": self.user.email, "password": self.new_password}
        )
        self.assertRedirects(response, reverse("accounts:pending"))

    def test_cuenta_desactivada_despues_de_emitir_enlace_conserva_bloqueo(self):
        self.request_link()
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        _, form_url, _ = self.open_link()
        self.assertEqual(self.reset(form_url).status_code, 302)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.client.post(
            reverse("account_login"), {"login": self.user.email, "password": self.new_password}
        )
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_contrasena_debil_o_confirmacion_distinta_conservan_clave_anterior(self):
        self.request_link()
        _, form_url, _ = self.open_link()
        for password1, password2 in (("123", "123"), (self.new_password, "otra")):
            with self.subTest(password=password1):
                response = self.reset(form_url, password1=password1, password2=password2)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
                self.user.refresh_from_db()
                self.assertTrue(self.user.check_password(self.old_password))
        self.assertEqual(self.reset(form_url).status_code, 302)

    def test_token_alterado_o_vencido_muestra_otro_enlace_de_solicitud(self):
        self.request_link()
        original_url, _, _ = self.open_link()
        invalid = self.client.get(original_url.rstrip("/") + "alterado/")
        self.assertContains(invalid, "Enlace no disponible")
        self.assertContains(invalid, f'href="{self.url}"')
        later = default_token_generator._now() + timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT + 1)
        with patch.object(default_token_generator, "_now", return_value=later):
            expired = self.client.get(original_url)
        self.assertContains(expired, "Enlace no disponible")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_password))

    def test_solicitud_y_cambio_exigen_csrf_y_aceptan_formularios_del_mismo_origen(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(self.url, {"email": self.user.email}).status_code, 403)
        client.get(self.url)
        response = client.post(
            self.url,
            {
                "email": self.user.email,
                "csrfmiddlewaretoken": client.cookies[settings.CSRF_COOKIE_NAME].value,
            },
            HTTP_ORIGIN="http://testserver",
        )
        self.assertEqual(response.status_code, 302)
        _, form_url, _ = self.open_link(client=client)
        fields = {"password1": self.new_password, "password2": self.new_password}
        self.assertEqual(client.post(form_url, fields).status_code, 403)
        fields["csrfmiddlewaretoken"] = client.cookies[settings.CSRF_COOKIE_NAME].value
        response = client.post(form_url, fields, HTTP_ORIGIN="http://testserver")
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))

    def test_enlace_sin_grupo_no_permite_redireccion_externa(self):
        self.request_link()
        _, form_url, _ = self.open_link()
        response = self.reset(form_url, next="https://ajeno.example/")
        self.assertEqual(urlsplit(response.url).netloc, "")

    def test_fallo_smtp_muestra_error_y_permite_reintentar_sin_cambiar_la_cuenta(self):
        with patch("django.core.mail.message.EmailMessage.send", side_effect=SMTPException("detalle-privado")):
            response = self.client.post(self.url, {"email": self.user.email})
        self.assertContains(response, "No se pudo enviar el correo de recuperación")
        self.assertNotContains(response, "detalle-privado")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_password))
        self.assertEqual(User.objects.count(), 1)
        self.request_link()
        self.assertEqual(len(mail.outbox), 1)

    def test_backend_sin_envio_no_muestra_confirmacion(self):
        with patch("django.core.mail.message.EmailMessage.send", return_value=0):
            response = self.client.post(self.url, {"email": self.user.email})
        self.assertContains(response, "No se pudo enviar el correo de recuperación")
        self.assertEqual(response.status_code, 200)

    def test_limite_de_solicitudes_por_correo(self):
        for _ in range(5):
            self.request_link()
        response = self.client.post(self.url, {"email": self.user.email})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(len(mail.outbox), 5)
