from urllib.parse import urlsplit

from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    SECURE_SSL_REDIRECT=False,
)
class AuthenticationTests(TestCase):
    password = "Clave-ficticia-para-pruebas-2026"

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_superuser(
            "admin@colegio.example", self.password
        )
        EmailAddress.objects.create(
            user=self.user,
            email=self.user.email,
            primary=True,
            verified=True,
        )

    def login(self, **extra):
        return self.client.post(
            reverse("account_login"),
            {"login": self.user.email, "password": self.password, **extra},
        )

    def test_inicio_redirige_al_formulario_de_acceso(self):
        self.assertRedirects(self.client.get("/"), reverse("account_login"))

    def test_formulario_pide_correo_y_contrasena(self):
        response = self.client.get(reverse("account_login"))
        self.assertContains(response, 'type="email"')
        self.assertContains(response, 'type="password"')
        self.assertNotIn("remember", response.context["form"].fields)
        self.assertContains(response, 'lang="es-CL"')

    def test_superusuario_verificado_accede_a_django_admin(self):
        response = self.login()
        self.assertRedirects(response, reverse("admin:index"))
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_acceso_normaliza_mayusculas_y_espacios(self):
        response = self.login(login="  ADMIN@COLEGIO.EXAMPLE  ")
        self.assertRedirects(response, reverse("admin:index"))

    def test_error_de_credenciales_no_revela_si_existe_el_correo(self):
        wrong_password = self.login(password="Contrasena-equivocada")
        unknown_email = self.login(login="desconocido@colegio.example")
        self.assertEqual(wrong_password.status_code, 200)
        self.assertEqual(unknown_email.status_code, 200)
        self.assertEqual(
            list(wrong_password.context["form"].non_field_errors()),
            list(unknown_email.context["form"].non_field_errors()),
        )
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_cuenta_inactiva_no_inicia_sesion(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.login()
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_correo_pendiente_requiere_verificacion(self):
        EmailAddress.objects.filter(user=self.user).update(verified=False)
        response = self.login()
        self.assertRedirects(response, reverse("account_email_verification_sent"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(settings.SITE_URL + "/accounts/confirm-email/", mail.outbox[0].body)

    def test_cuenta_previa_a_allauth_puede_verificar_correo(self):
        EmailAddress.objects.filter(user=self.user).delete()
        response = self.login()
        self.assertRedirects(response, reverse("account_email_verification_sent"))
        address = EmailAddress.objects.get(user=self.user)
        self.assertFalse(address.verified)
        confirmation = EmailConfirmationHMAC(address)
        url = reverse("account_confirm_email", args=[confirmation.key])
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.client.post(url)
        address.refresh_from_db()
        self.assertTrue(address.verified)
        self.assertRedirects(self.login(), reverse("admin:index"))

    def test_ruta_admin_login_usa_allauth_y_no_autentica_por_post(self):
        response = self.client.get("/admin/login/?next=/admin/")
        self.assertEqual(response.url, reverse("account_login") + "?next=/admin/")
        self.client.post(
            "/admin/login/",
            {"username": self.user.email, "password": self.password},
        )
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_registro_publico_get_y_post_no_crea_cuentas(self):
        count = User.objects.count()
        get_response = self.client.get(reverse("account_signup"))
        post_response = self.client.post(
            reverse("account_signup"),
            {
                "email": "invitado@colegio.example",
                "password1": self.password,
                "password2": self.password,
                "is_superuser": "true",
                "groups": "administrador",
            },
        )
        self.assertContains(get_response, "Acceso por invitación")
        self.assertContains(post_response, "Acceso por invitación")
        self.assertEqual(User.objects.count(), count)

    def test_get_logout_conserva_la_sesion_y_post_la_cierra(self):
        self.login()
        response = self.client.get(reverse("account_logout"))
        self.assertContains(response, "Confirma que deseas cerrar tu sesión")
        self.assertIn("_auth_user_id", self.client.session)
        self.assertRedirects(
            self.client.post(reverse("account_logout")), reverse("account_login")
        )
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)

    def test_login_y_logout_exigen_csrf(self):
        client = Client(enforce_csrf_checks=True)
        url = reverse("account_login")
        self.assertEqual(
            client.post(url, {"login": self.user.email, "password": self.password}).status_code,
            403,
        )
        client.get(url)
        token = client.cookies[settings.CSRF_COOKIE_NAME].value
        response = client.post(
            url,
            {"login": self.user.email, "password": self.password, "csrfmiddlewaretoken": token},
        )
        self.assertEqual(response.status_code, 302)
        logout = reverse("account_logout")
        self.assertEqual(client.post(logout).status_code, 403)
        token = client.cookies[settings.CSRF_COOKIE_NAME].value
        response = client.post(logout, {"csrfmiddlewaretoken": token})
        self.assertEqual(response.status_code, 302)

    def test_next_externo_no_redirige_fuera_del_sitio(self):
        response = self.login(next="https://ajeno.example/recibir")
        self.assertEqual(urlsplit(response.url).netloc, "")
        self.assertRedirects(response, reverse("admin:index"))

    def test_intentos_fallidos_activan_limite_de_acceso(self):
        for _ in range(5):
            self.login(password="Contrasena-equivocada")
        response = self.login()
        self.assertEqual(response.status_code, 200)
        errors = response.context["form"].non_field_errors().as_data()
        self.assertEqual(errors[0].code, "too_many_login_attempts")
        self.assertNotIn("_auth_user_id", self.client.session)
