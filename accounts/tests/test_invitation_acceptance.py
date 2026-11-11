import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth.models import Group
from django.core import mail
from django.core.cache import cache
from django.db import IntegrityError, close_old_connections, connections, transaction
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.logging import InvitationTokenFilter
from accounts.models import Invitation, User
from accounts.services import InvalidInvitation, accept_invitation, send_invitation
from accounts.tests.test_invitations import email_token


class InvitationLoggingTests(SimpleTestCase):
    @override_settings(DEBUG=True)
    def test_registros_de_django_ocultan_token(self):
        for name in ("django.server", "django.request", "django.security.csrf"):
            handlers = logging.getLogger("django.server" if name == "django.server" else "django").handlers
            self.assertTrue(handlers)
            for handler in handlers:
                with self.subTest(logger=name, handler=handler.name):
                    record = logging.LogRecord(
                        name, logging.INFO, __file__, 1,
                        '"GET %s HTTP/1.1" 200',
                        ("/accounts/invitations/accept/token-de-prueba/",), None,
                    )
                    handler.filter(record)
                    self.assertNotIn("token-de-prueba", record.getMessage())
                    self.assertIn("/accounts/invitations/accept/[oculto]/", record.getMessage())
                    self.assertTrue(any(
                        isinstance(item, InvitationTokenFilter) for item in handler.filters
                    ))
        self.assertTrue(logging.getLogger("django.server").handlers)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class InvitationAcceptanceTests(TestCase):
    password = "Clave-ficticia-para-pruebas-2026"

    @classmethod
    def setUpTestData(cls):
        cls.sender = User.objects.create_superuser("emisor@colegio.example")

    def setUp(self):
        cache.clear()
        self.invitation = send_invitation(
            email=" Persona.Apellido+PIE@Colegio.EXAMPLE ", invited_by=self.sender
        )
        self.token = email_token(mail.outbox[-1])
        self.url = reverse("accounts:invitation_accept", args=[self.token])

    def submit(self, **extra):
        return self.client.post(
            self.url,
            {"new_password1": self.password, "new_password2": self.password, **extra},
        )

    def assert_unavailable(self, response):
        self.assertContains(response, "Invitación no disponible", status_code=400)
        self.assertNotContains(response, self.invitation.email, status_code=400)
        self.assertNotContains(response, 'type="password"', status_code=400)

    def test_get_muestra_correo_de_solo_lectura_sin_consumir_invitacion(self):
        for _ in range(2):
            response = self.client.get(self.url)
            self.assertContains(response, self.invitation.email)
            self.assertNotContains(response, 'name="email"')
            self.assertContains(response, 'name="new_password1"')
            self.assertContains(response, 'name="new_password2"')
            self.assertEqual(response.headers["Referrer-Policy"], "strict-origin")
            self.assertIn("no-store", response.headers["Cache-Control"])
        self.invitation.refresh_from_db()
        self.assertIsNone(self.invitation.accepted_at)
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(EmailAddress.objects.exists())

    def test_post_crea_cuenta_activa_verificada_sin_roles_e_inicia_en_espera(self):
        response = self.submit(
            email="otra@colegio.example",
            groups=[Group.objects.get(name="administrador").pk],
            invited_by=self.sender.pk,
            is_superuser="true",
            is_staff="true",
            is_active="false",
            next="https://ajeno.example/",
        )
        self.assertRedirects(response, reverse("account_login"))
        user = User.objects.get(email=self.invitation.email)
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password(self.password))
        self.assertFalse(user.groups.exists())
        self.assertFalse(user.user_permissions.exists())
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(User.objects.count(), 2)
        address = EmailAddress.objects.get(user=user)
        self.assertEqual(address.email, self.invitation.email)
        self.assertTrue(address.primary)
        self.assertTrue(address.verified)
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.accepted_user, user)
        self.assertIsNotNone(self.invitation.accepted_at)
        self.assertNotIn("_auth_user_id", self.client.session)
        login = self.client.post(
            reverse("account_login"), {"login": user.email, "password": self.password}
        )
        self.assertRedirects(login, reverse("accounts:pending"))
        self.assertEqual(len(mail.outbox), 1)

    def test_contrasena_invalida_o_confirmacion_distinta_no_consume_invitacion(self):
        for password1, password2 in (("123", "123"), (self.password, "diferente")):
            with self.subTest(password=password1):
                response = self.submit(new_password1=password1, new_password2=password2)
                self.assertEqual(response.status_code, 200)
                self.assertIn("new_password2", response.context["form"].errors)
        self.invitation.refresh_from_db()
        self.assertIsNone(self.invitation.accepted_at)
        self.assertEqual(User.objects.count(), 1)

    def test_post_sin_csrf_no_crea_cuenta(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(
            self.url, {"new_password1": self.password, "new_password2": self.password}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(User.objects.count(), 1)
        self.invitation.refresh_from_db()
        self.assertIsNone(self.invitation.accepted_at)

    @override_settings(ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"])
    def test_formulario_con_csrf_acepta_el_origen_del_servidor(self):
        for index, (host, secure) in enumerate((
            ("localhost:8000", False),
            ("127.0.0.1:8000", False),
            ("testserver", True),
        )):
            with self.subTest(host=host, secure=secure):
                email = f"aceptacion-{index}@colegio.example"
                send_invitation(email=email, invited_by=self.sender)
                url = reverse("accounts:invitation_accept", args=[email_token(mail.outbox[-1])])
                client = Client(enforce_csrf_checks=True)
                page = client.get(url, HTTP_HOST=host, secure=secure)
                self.assertEqual(page.headers["Referrer-Policy"], "strict-origin")
                csrf_token = client.cookies[settings.CSRF_COOKIE_NAME].value
                origin = f"{'https' if secure else 'http'}://{host}"
                response = client.post(
                    url,
                    {
                        "new_password1": self.password,
                        "new_password2": self.password,
                        "csrfmiddlewaretoken": csrf_token,
                    },
                    HTTP_HOST=host,
                    HTTP_ORIGIN=origin,
                    HTTP_REFERER=origin + "/",
                    secure=secure,
                )
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.url, reverse("account_login"))
                self.assertTrue(User.objects.filter(email=email).exists())

    def test_origen_nulo_o_ajeno_se_rechaza_incluso_con_token_csrf_valido(self):
        client = Client(enforce_csrf_checks=True)
        client.get(self.url)
        csrf_token = client.cookies[settings.CSRF_COOKIE_NAME].value
        for origin in ("null", "https://ajeno.example"):
            with self.subTest(origin=origin):
                response = client.post(
                    self.url,
                    {
                        "new_password1": self.password,
                        "new_password2": self.password,
                        "csrfmiddlewaretoken": csrf_token,
                    },
                    HTTP_ORIGIN=origin,
                )
                self.assertEqual(response.status_code, 403)
        self.assertEqual(User.objects.count(), 1)
        self.invitation.refresh_from_db()
        self.assertIsNone(self.invitation.accepted_at)

    def test_https_acepta_referer_de_solo_origen_sin_cabecera_origin(self):
        client = Client(enforce_csrf_checks=True)
        client.get(self.url, secure=True)
        response = client.post(
            self.url,
            {
                "new_password1": self.password,
                "new_password2": self.password,
                "csrfmiddlewaretoken": client.cookies[settings.CSRF_COOKIE_NAME].value,
            },
            HTTP_REFERER="https://testserver/",
            secure=True,
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(email=self.invitation.email).exists())

    def test_token_invalido_no_revela_destinatario_por_get_ni_post(self):
        url = reverse("accounts:invitation_accept", args=["token-invalido"])
        self.assert_unavailable(self.client.get(url))
        self.assert_unavailable(self.client.post(url, {
            "new_password1": self.password, "new_password2": self.password,
        }))
        self.assertEqual(User.objects.count(), 1)

    def test_aceptacion_vence_exactamente_a_las_48_horas(self):
        for moment in (self.invitation.expires_at, self.invitation.expires_at + timedelta(seconds=1)):
            with self.subTest(moment=moment):
                with patch("accounts.models.timezone.now", return_value=moment):
                    self.assert_unavailable(self.client.get(self.url))
                    self.assert_unavailable(self.submit())
        self.assertEqual(User.objects.count(), 1)

    def test_aceptacion_funciona_justo_antes_del_vencimiento(self):
        moment = self.invitation.expires_at - timedelta(microseconds=1)
        with patch("accounts.models.timezone.now", return_value=moment):
            self.assertRedirects(self.submit(), reverse("account_login"))
        self.assertTrue(User.objects.filter(email=self.invitation.email).exists())

    def test_enlace_consumido_no_modifica_contrasena_ni_crea_otro_usuario(self):
        self.submit()
        user = User.objects.get(email=self.invitation.email)
        password_hash = user.password
        self.assert_unavailable(self.client.get(self.url))
        self.assert_unavailable(self.submit(
            new_password1="Otra-clave-ficticia-para-pruebas",
            new_password2="Otra-clave-ficticia-para-pruebas",
        ))
        user.refresh_from_db()
        self.assertEqual(user.password, password_hash)
        self.assertEqual(User.objects.count(), 2)

    def test_reenviar_invalida_formulario_ya_abierto(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        send_invitation(email=self.invitation.email, invited_by=self.sender)
        self.assert_unavailable(self.submit())
        new_token = email_token(mail.outbox[-1])
        new_url = reverse("accounts:invitation_accept", args=[new_token])
        self.assertEqual(self.client.get(new_url).status_code, 200)
        self.assertEqual(User.objects.count(), 1)

    def test_cuenta_creada_despues_de_enviar_no_es_reemplazada(self):
        existing = User.objects.create_user(self.invitation.email, self.password, is_active=False)
        password_hash = existing.password
        self.assert_unavailable(self.submit())
        existing.refresh_from_db()
        self.assertFalse(existing.is_active)
        self.assertEqual(existing.password, password_hash)
        self.assertEqual(User.objects.count(), 2)
        self.invitation.refresh_from_db()
        self.assertIsNone(self.invitation.accepted_at)

    def test_colision_de_correo_en_allauth_no_deja_usuario_parcial(self):
        EmailAddress.objects.create(
            user=self.sender, email=self.invitation.email, primary=True, verified=True
        )
        self.assert_unavailable(self.submit())
        self.assertFalse(User.objects.filter(email=self.invitation.email).exists())
        self.assertEqual(EmailAddress.objects.count(), 1)

    def test_conflicto_de_unicidad_revierte_usuario_y_consumo(self):
        with patch("accounts.adapters.EmailAddress.objects.create", side_effect=IntegrityError):
            self.assert_unavailable(self.submit())
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(EmailAddress.objects.exists())
        self.invitation.refresh_from_db()
        self.assertIsNone(self.invitation.accepted_at)

    def test_vencimiento_durante_alta_revierte_usuario_y_consumo(self):
        with patch("accounts.adapters.AccountAdapter.confirm_invited_email", side_effect=InvalidInvitation):
            self.assert_unavailable(self.submit())
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(EmailAddress.objects.exists())

    def test_sesion_de_otro_usuario_no_recibe_el_correo_del_invitado(self):
        self.client.force_login(self.sender)
        self.assertRedirects(self.submit(), reverse("account_login"), fetch_redirect_response=False)
        self.sender.refresh_from_db()
        self.assertEqual(self.sender.email, "emisor@colegio.example")
        self.assertFalse(EmailAddress.objects.filter(user=self.sender).exists())
        self.assertTrue(EmailAddress.objects.get(email=self.invitation.email).verified)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class InvitationAcceptanceConcurrencyTests(TransactionTestCase):
    password = "Clave-ficticia-para-pruebas-2026"

    def setUp(self):
        sender = User.objects.create_superuser("emisor@colegio.example")
        self.invitation = send_invitation(email="persona@colegio.example", invited_by=sender)
        self.token = email_token(mail.outbox[-1])

    def test_dos_aceptaciones_concurrentes_crean_una_cuenta_verificada(self):
        barrier = Barrier(2)

        def accept():
            close_old_connections()
            try:
                request = RequestFactory().post("/")
                barrier.wait(timeout=10)
                user = accept_invitation(request=request, token=self.token, password=self.password)
                return user.pk
            except InvalidInvitation:
                return None
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: accept(), range(2)))
        self.assertEqual(results.count(None), 1)
        user = User.objects.get(email=self.invitation.email)
        self.assertIn(user.pk, results)
        self.assertTrue(user.check_password(self.password))
        self.assertEqual(EmailAddress.objects.filter(user=user, primary=True, verified=True).count(), 1)
        self.assertEqual(User.objects.count(), 2)
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.accepted_user, user)

    def test_cuenta_concurrente_con_mayusculas_revierte_aceptacion_completa(self):
        barrier = Barrier(2)
        real_create_user = User.objects.create_user

        def create_invited_user(email, password):
            barrier.wait(timeout=10)
            barrier.wait(timeout=10)
            return real_create_user(email, password)

        def accept():
            close_old_connections()
            try:
                request = RequestFactory().post("/")
                return accept_invitation(request=request, token=self.token, password=self.password)
            except InvalidInvitation:
                return None
            finally:
                connections.close_all()

        with patch("accounts.services.User.objects.create_user", side_effect=create_invited_user):
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(accept)
                barrier.wait(timeout=10)
                with transaction.atomic():
                    User.objects.bulk_create([User(email=self.invitation.email.upper())])
                barrier.wait(timeout=10)
                self.assertIsNone(future.result(timeout=15))
        self.assertEqual(User.objects.count(), 2)
        self.assertFalse(EmailAddress.objects.exists())
        self.invitation.refresh_from_db()
        self.assertIsNone(self.invitation.accepted_at)
        self.assertIsNone(self.invitation.accepted_user)
