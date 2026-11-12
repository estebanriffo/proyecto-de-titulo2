import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from smtplib import SMTPException
from threading import Barrier
from unittest.mock import patch

from allauth.account.models import EmailAddress
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, close_old_connections, connections, transaction
from django.test import Client, SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.forms import InvitationForm
from accounts.models import Invitation, User
from accounts.services import InvitationDeliveryError, send_invitation


def email_token(message):
    return re.search(r"/accept/([A-Za-z0-9_-]+)/", message.body).group(1)


class InvitationValidationTests(SimpleTestCase):
    def test_formulario_normaliza_sin_alterar_puntos_o_sufijos(self):
        form = InvitationForm({"email": " Persona.Apellido+PIE@Colegio.EXAMPLE "})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["email"], "persona.apellido+pie@colegio.example")

    def test_formulario_rechaza_correo_invalido_largo_o_con_cabeceras(self):
        for email in (
            "sin-arroba",
            "a" * 250 + "@example.com",
            "persona@example.com\nBcc:otro@example.com",
        ):
            with self.subTest(email=email):
                self.assertFalse(InvitationForm({"email": email}).is_valid())

    def test_estado_derivado_vence_exactamente_a_las_48_horas(self):
        sent_at = timezone.now()
        invitation = Invitation(sent_at=sent_at, expires_at=sent_at + timedelta(hours=48))
        before_expiry = invitation.expires_at - timedelta(microseconds=1)
        with patch("accounts.models.timezone.now", return_value=before_expiry):
            self.assertTrue(invitation.is_available)
            self.assertEqual(invitation.status, "pendiente")
        with patch("accounts.models.timezone.now", return_value=invitation.expires_at):
            self.assertFalse(invitation.is_available)
            self.assertEqual(invitation.status, "vencida")

    def test_invitacion_aceptada_permanece_consumida(self):
        now = timezone.now()
        invitation = Invitation(accepted_at=now, expires_at=now + timedelta(hours=48))
        self.assertFalse(invitation.is_available)
        self.assertEqual(invitation.status, "aceptada")


@override_settings(
    SECURE_SSL_REDIRECT=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    SITE_URL="https://aprendo.example",
)
class InvitationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user("docente@colegio.example")
        cls.teacher.groups.add(Group.objects.get(name="docente"))
        EmailAddress.objects.create(
            user=cls.teacher, email=cls.teacher.email, primary=True, verified=True
        )

    def setUp(self):
        self.url = reverse("accounts:invitations")
        self.client.force_login(self.teacher)

    def test_docente_administrador_y_superusuario_pueden_enviar_sin_crear_cuenta(self):
        initial_users = User.objects.count()
        for role in ("docente", "administrador", "superusuario"):
            with self.subTest(role=role):
                self.teacher.groups.set(Group.objects.filter(name=role))
                self.teacher.is_superuser = role == "superusuario"
                self.teacher.save(update_fields=["is_superuser"])
                self.assertContains(self.client.get(self.url), 'name="email"')
                response = self.client.post(
                    self.url,
                    {
                        "email": "  Persona.Apellido+PIE@Colegio.EXAMPLE  ",
                        "invited_by": "99999",
                        "groups": "administrador",
                        "is_superuser": "true",
                    },
                )
                self.assertRedirects(response, self.url)
                invitation = Invitation.objects.get(email="persona.apellido+pie@colegio.example")
                self.assertEqual(invitation.invited_by, self.teacher)
                self.assertEqual(invitation.expires_at - invitation.sent_at, timedelta(hours=48))
                self.assertIsNone(invitation.accepted_at)
                self.assertIsNone(invitation.accepted_user)
                self.assertEqual(User.objects.count(), initial_users)
                self.assertEqual(EmailAddress.objects.count(), 1)
        self.assertEqual(Invitation.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 3)
        token = email_token(mail.outbox[-1])
        self.assertEqual(invitation.token_digest, hashlib.sha256(token.encode()).hexdigest())
        self.assertNotIn(token, str(invitation.__dict__))
        self.assertNotIn(token, str(response.content))
        self.assertEqual(mail.outbox[-1].to, [invitation.email])

    def test_visitante_no_puede_abrir_ni_enviar_invitaciones(self):
        self.client.logout()
        for method in (self.client.get, self.client.post):
            response = method(self.url, {"email": "persona@colegio.example"})
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith(reverse("account_login")))
        self.assertFalse(Invitation.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_estudiante_sin_grupo_y_staff_no_pueden_invitar(self):
        self.teacher.is_staff = True
        self.teacher.save(update_fields=["is_staff"])
        self.teacher.user_permissions.add(Permission.objects.get(codename="add_invitation"))
        for role in ("estudiante", None):
            with self.subTest(role=role):
                self.teacher.groups.set(Group.objects.filter(name=role))
                self.assertEqual(self.client.get(self.url).status_code, 403)
                self.assertEqual(
                    self.client.post(self.url, {"email": "persona@colegio.example"}).status_code,
                    403,
                )
                with self.assertRaises(PermissionDenied):
                    send_invitation(email="persona@colegio.example", invited_by=self.teacher)
        self.assertFalse(Invitation.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_retirar_rol_revoca_envio_con_sesion_abierta(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.teacher.groups.set(Group.objects.filter(name="estudiante"))
        self.assertNotContains(self.client.get(reverse("accounts:authorized")), "Enviar invitaciones")
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(
            self.client.post(self.url, {"email": "persona@colegio.example"}).status_code, 403
        )
        self.assertFalse(Invitation.objects.exists())

    def test_roles_educativos_incompatibles_no_permiten_invitar(self):
        self.teacher.groups.add(Group.objects.get(name="estudiante"))
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(
            self.client.post(self.url, {"email": "persona@colegio.example"}).status_code, 403
        )
        with self.assertRaises(PermissionDenied):
            send_invitation(email="persona@colegio.example", invited_by=self.teacher)
        self.assertFalse(Invitation.objects.exists())

    def test_enlace_a_invitaciones_solo_aparece_para_roles_autorizados(self):
        home = reverse("accounts:authorized")
        self.assertContains(self.client.get(home), "Enviar invitaciones")
        self.teacher.groups.set(Group.objects.filter(name="estudiante"))
        self.assertNotContains(self.client.get(home), "Enviar invitaciones")

    def test_correo_invalido_y_demasiado_largo_rechazados(self):
        for email in ("sin-arroba", "a" * 250 + "@example.com", "persona@example.com\nBcc:otro@example.com"):
            with self.subTest(email=email):
                response = self.client.post(self.url, {"email": email})
                self.assertEqual(response.status_code, 200)
                self.assertIn("email", response.context["form"].errors)
        self.assertFalse(Invitation.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_get_solo_muestra_el_formulario(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'for="id_email"')
        self.assertContains(response, 'type="email"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertFalse(Invitation.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_envio_exige_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.teacher)
        response = client.post(self.url, {"email": "persona@colegio.example"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Invitation.objects.exists())

    @override_settings(ALLOWED_HOSTS=["testserver", "ajeno.example"])
    def test_enlace_usa_site_url_y_solo_se_envia_al_destinatario(self):
        response = self.client.post(
            self.url, {"email": "persona@colegio.example"}, HTTP_HOST="ajeno.example"
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("https://aprendo.example/accounts/invitations/accept/", mail.outbox[0].body)
        self.assertNotIn("ajeno.example", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ["persona@colegio.example"])

    def test_reenvio_rota_token_y_reinicia_vigencia_sin_cambiar_identificador(self):
        first_time = timezone.now()
        with patch("accounts.services.timezone.now", return_value=first_time):
            first = send_invitation(email="persona@colegio.example", invited_by=self.teacher)
        old_digest = first.token_digest
        old_created_at = first.created_at
        later = first_time + timedelta(hours=49)
        with patch("accounts.services.timezone.now", return_value=later):
            renewed = send_invitation(email="PERSONA@COLEGIO.EXAMPLE", invited_by=self.teacher)
            self.assertTrue(renewed.is_available)
        self.assertEqual(renewed.pk, first.pk)
        self.assertEqual(renewed.created_at, old_created_at)
        self.assertEqual(renewed.sent_at, later)
        self.assertEqual(renewed.expires_at, later + timedelta(hours=48))
        self.assertNotEqual(renewed.token_digest, old_digest)
        self.assertFalse(Invitation.objects.filter(token_digest=old_digest).exists())
        self.assertNotEqual(email_token(mail.outbox[0]), email_token(mail.outbox[1]))

    def test_cuenta_existente_incluso_inactiva_no_recibe_invitacion(self):
        User.objects.create_user("persona@colegio.example", is_active=False)
        response = self.client.post(self.url, {"email": " PERSONA@COLEGIO.EXAMPLE "})
        self.assertContains(response, "Ya existe una cuenta")
        self.assertIn("email", response.context["form"].errors)
        self.assertFalse(Invitation.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_correo_asociado_en_allauth_no_se_asigna_a_otra_cuenta(self):
        EmailAddress.objects.create(
            user=self.teacher, email="persona@colegio.example", primary=False, verified=True
        )
        with self.assertRaises(ValidationError):
            send_invitation(email="persona@colegio.example", invited_by=self.teacher)
        self.assertFalse(Invitation.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_invitacion_aceptada_no_se_renueva(self):
        invitation = send_invitation(email="persona@colegio.example", invited_by=self.teacher)
        Invitation.objects.filter(pk=invitation.pk).update(accepted_at=timezone.now())
        with self.assertRaises(ValidationError):
            send_invitation(email=invitation.email, invited_by=self.teacher)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "aceptada")
        self.assertEqual(len(mail.outbox), 1)

    def test_fallo_smtp_muestra_error_sin_cuenta_ni_invitacion(self):
        with patch("accounts.services.send_mail", side_effect=SMTPException("detalle-privado")):
            response = self.client.post(self.url, {"email": "persona@colegio.example"})
        self.assertContains(response, "No se pudo enviar el correo")
        self.assertNotContains(response, "detalle-privado")
        self.assertNotContains(response, "Invitación enviada")
        self.assertFalse(Invitation.objects.exists())
        self.assertEqual(User.objects.count(), 1)

    def test_backend_que_no_envia_informa_fallo(self):
        with patch("accounts.services.send_mail", return_value=0):
            with self.assertRaises(InvitationDeliveryError):
                send_invitation(email="persona@colegio.example", invited_by=self.teacher)
        self.assertFalse(Invitation.objects.exists())

    def test_fallo_de_reenvio_revierte_renovacion_y_permite_reintentar(self):
        invitation = send_invitation(email="persona@colegio.example", invited_by=self.teacher)
        old_digest = invitation.token_digest
        old_sent_at = invitation.sent_at
        with patch("accounts.services.send_mail", side_effect=OSError("detalle-privado")):
            with self.assertRaises(InvitationDeliveryError):
                send_invitation(email=invitation.email, invited_by=self.teacher)
        invitation.refresh_from_db()
        self.assertEqual(invitation.token_digest, old_digest)
        self.assertEqual(invitation.sent_at, old_sent_at)
        renewed = send_invitation(email=invitation.email, invited_by=self.teacher)
        self.assertNotEqual(renewed.token_digest, old_digest)

    def test_restricciones_postgresql_rechazan_duplicados_y_espacios_directos(self):
        invitation = send_invitation(email="persona@colegio.example", invited_by=self.teacher)
        for email in ("PERSONA@COLEGIO.EXAMPLE", " otro@colegio.example", "otro@colegio.example "):
            with self.subTest(email=email):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Invitation.objects.bulk_create([
                        Invitation(
                            email=email,
                            token_digest=hashlib.sha256(email.encode()).hexdigest(),
                            sent_at=invitation.sent_at,
                            expires_at=invitation.expires_at,
                        )
                    ])

    def test_eliminar_emisor_conserva_invitacion_sin_referencia(self):
        invitation = send_invitation(email="persona@colegio.example", invited_by=self.teacher)
        self.teacher.delete()
        invitation.refresh_from_db()
        self.assertIsNone(invitation.invited_by)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class InvitationConcurrencyTests(TransactionTestCase):
    def run_concurrent_sends(self, *, existing):
        # TransactionTestCase limpia los grupos de la migración al vaciar la base.
        teacher = User.objects.create_superuser("emisor@colegio.example")
        recipient = "persona@colegio.example"
        if existing:
            send_invitation(email=recipient, invited_by=teacher)
        barrier = Barrier(2)

        def send(email):
            close_old_connections()
            try:
                actor = User.objects.get(pk=teacher.pk)
                barrier.wait(timeout=10)
                invitation = send_invitation(email=email, invited_by=actor)
                return invitation.pk, invitation.token_digest
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(send, [recipient, recipient.upper()]))
        invitation = Invitation.objects.get(email=recipient)
        self.assertEqual({pk for pk, _ in results}, {invitation.pk})
        self.assertEqual(len({digest for _, digest in results}), 2)
        self.assertEqual(sum(digest == invitation.token_digest for _, digest in results), 1)
        self.assertEqual(Invitation.objects.count(), 1)
        self.assertEqual(User.objects.count(), 1)

    def test_dos_emisiones_iniciales_dejan_un_solo_token_vigente(self):
        self.run_concurrent_sends(existing=False)

    def test_dos_reenvios_dejan_un_solo_token_vigente(self):
        self.run_concurrent_sends(existing=True)
