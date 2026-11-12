from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from allauth.account.models import EmailAddress
from django.contrib.auth.models import Group, Permission
from django.core.cache import cache
from django.db import connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from accounts.access import ROLE_NAMES
from accounts.models import User


@override_settings(SECURE_SSL_REDIRECT=False)
class AccessTests(TestCase):
    password = "Clave-ficticia-para-pruebas-2026"

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("persona@colegio.example", self.password)
        EmailAddress.objects.create(
            user=self.user, email=self.user.email, primary=True, verified=True
        )

    def assign(self, *roles):
        self.user.groups.set(Group.objects.filter(name__in=roles))

    def login(self):
        return self.client.post(
            reverse("account_login"),
            {"login": self.user.email, "password": self.password},
        )

    def test_migracion_crea_grupos_y_permisos_de_gestion(self):
        self.assertEqual(set(Group.objects.values_list("name", flat=True)), set(ROLE_NAMES))
        administrator = Group.objects.get(name="administrador")
        self.assertEqual(
            set(administrator.permissions.values_list("codename", flat=True)),
            {"view_user", "change_user"},
        )
        self.assertFalse(Group.objects.get(name="docente").permissions.exists())
        self.assertFalse(Group.objects.get(name="estudiante").permissions.exists())

    def test_visitante_no_accede_a_las_pantallas_protegidas(self):
        for name in ("accounts:authorized", "accounts:pending"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith(reverse("account_login")))

    def test_cuenta_sin_grupo_inicia_en_espera(self):
        self.assertRedirects(self.login(), reverse("accounts:pending"))
        response = self.client.get(reverse("accounts:pending"))
        self.assertContains(response, "pendiente de autorización")
        self.assertNotContains(response, "Gestionar cuentas")
        self.assertContains(response, "Cerrar sesión")
        self.assertRedirects(
            self.client.get(reverse("accounts:authorized")), reverse("accounts:pending")
        )

    def test_cada_rol_accede_a_la_pantalla_autorizada(self):
        options = {
            "estudiante": ("<li>Actividades</li>", "<li>Mi progreso</li>"),
            "docente": ("<li>Gestionar actividades</li>", "<li>Revisar progreso de estudiantes</li>"),
        }
        for role in ROLE_NAMES:
            with self.subTest(role=role):
                self.assign(role)
                self.assertRedirects(self.login(), reverse("accounts:authorized"))
                response = self.client.get(reverse("accounts:authorized"))
                self.assertContains(response, role.capitalize())
                self.assertEqual(response.context["can_manage_accounts"], role == "administrador")
                for profile, items in options.items():
                    for item in items:
                        assertion = self.assertContains if role == profile else self.assertNotContains
                        assertion(response, item, html=True)
                self.assertEqual("Próximamente" in response.content.decode(), role in options)
                self.client.logout()

    def test_asignar_y_retirar_grupos_aplica_en_la_siguiente_solicitud(self):
        self.login()
        self.assign("docente")
        response = self.client.get(reverse("accounts:authorized"))
        self.assertContains(response, "Docente")
        self.assertContains(response, "Enviar invitaciones")
        self.assertRedirects(
            self.client.get(reverse("accounts:pending")), reverse("accounts:authorized")
        )
        self.assign()
        self.assertRedirects(
            self.client.get(reverse("accounts:authorized")), reverse("accounts:pending")
        )
        self.assertContains(self.client.get(reverse("accounts:pending")), "pendiente")

    def test_inicio_bloquea_funciones_educativas_con_roles_incompatibles(self):
        self.assign("estudiante", "docente")
        self.login()
        response = self.client.get(reverse("accounts:authorized"))
        self.assertContains(response, "Contacta a un administrador")
        self.assertNotContains(response, "Próximamente")
        self.assertNotContains(response, "Enviar invitaciones")
        self.assign("docente")
        self.assertContains(self.client.get(reverse("accounts:authorized")), "Enviar invitaciones")

    def test_admin_rechaza_roles_incompatibles_y_permite_cambiar_o_corregir_el_rol(self):
        self.assign("administrador")
        self.login()
        target = User.objects.create_user("otra@colegio.example", self.password)
        student = Group.objects.get(name="estudiante")
        teacher = Group.objects.get(name="docente")
        target.groups.add(student)
        url = reverse("admin:accounts_user_change", args=[target.pk])

        response = self.client.post(url, {"is_active": "on", "groups": [student.pk, teacher.pk]})
        self.assertContains(response, "Selecciona solo uno de los roles")
        self.assertEqual(list(target.groups.all()), [student])
        response = self.client.post(url, {"is_active": "on", "groups": [teacher.pk]})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(target.groups.all()), [teacher])

        target.groups.add(student)
        response = self.client.post(url, {"is_active": "on", "groups": [student.pk]})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(target.groups.all()), [student])

    def test_grupo_ajeno_no_habilita_acceso(self):
        self.user.groups.add(Group.objects.create(name="otro"))
        self.assertRedirects(self.login(), reverse("accounts:pending"))

    def test_administrador_gestiona_cuentas_sin_indicadores_internos(self):
        self.assign("administrador")
        target = User.objects.create_user("otra@colegio.example", self.password)
        self.login()
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)
        url = reverse("admin:accounts_user_change", args=[target.pk])
        response = self.client.get(url)
        self.assertContains(response, 'name="groups"')
        self.assertNotContains(response, 'name="is_superuser"')
        self.assertNotContains(response, 'name="is_staff"')
        response = self.client.post(
            url,
            {
                "is_active": "on",
                "groups": [Group.objects.get(name="docente").pk],
                "is_superuser": "on",
                "is_staff": "on",
                "user_permissions": [Permission.objects.get(codename="add_user").pk],
                "email": self.user.email,
                "_save": "Guardar",
            },
        )
        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        self.assertEqual(list(target.groups.values_list("name", flat=True)), ["docente"])
        self.assertEqual(target.email, "otra@colegio.example")
        self.assertFalse(target.is_staff)
        self.assertFalse(target.is_superuser)
        self.assertFalse(target.user_permissions.exists())

    def test_docente_estudiante_y_staff_no_pueden_modificar_roles(self):
        url = reverse("admin:accounts_user_change", args=[self.user.pk])
        for role in ("docente", "estudiante", None):
            with self.subTest(role=role):
                self.assign(*([role] if role else []))
                self.user.is_staff = True
                self.user.save(update_fields=["is_staff"])
                self.login()
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(
                    self.client.post(url, {"groups": [Group.objects.get(name="administrador").pk]}).status_code,
                    403,
                )
                self.assertFalse(self.user.groups.filter(name="administrador").exists())
                self.client.logout()

    def test_retirar_grupo_administrador_revoca_admin_en_la_siguiente_solicitud(self):
        self.assign("administrador")
        self.login()
        url = reverse("admin:accounts_user_changelist")
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assign()
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_administrador_no_modifica_superusuarios_ni_crea_grupos_libres(self):
        self.assign("administrador")
        root = User.objects.create_superuser("root@colegio.example", self.password)
        self.login()
        url = reverse("admin:accounts_user_change", args=[root.pk])
        self.client.post(url, {"groups": [], "is_active": ""})
        root.refresh_from_db()
        self.assertTrue(root.is_active)
        self.assertTrue(root.is_superuser)
        other = Group.objects.create(name="otro")
        url = reverse("admin:accounts_user_change", args=[self.user.pk])
        response = self.client.post(url, {"is_active": "on", "groups": [other.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["adminform"].form.errors["groups"])
        self.assertFalse(self.user.groups.filter(pk=other.pk).exists())
        self.assertEqual(self.client.get("/admin/auth/group/add/").status_code, 404)

    def test_administracion_no_permite_alta_directa_ni_eliminacion(self):
        self.assign("administrador")
        self.login()
        self.assertEqual(self.client.get(reverse("admin:accounts_user_add")).status_code, 403)
        url = reverse("admin:accounts_user_delete", args=[self.user.pk])
        self.assertEqual(self.client.post(url, {"post": "yes"}).status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_cuenta_desactivada_pierde_acceso_con_sesion_abierta(self):
        self.assign("docente")
        self.login()
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.get(reverse("accounts:authorized"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("account_login")))

    def test_inicio_usa_roles_actuales_y_paginas_no_se_guardan_en_cache(self):
        self.assign("estudiante")
        self.login()
        self.assertRedirects(self.client.get("/"), reverse("accounts:authorized"))
        response = self.client.get(reverse("accounts:authorized"))
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_destino_admin_sin_permiso_responde_sin_ciclo_de_redirecciones(self):
        self.assign("estudiante")
        response = self.client.post(
            reverse("account_login"),
            {"login": self.user.email, "password": self.password, "next": "/admin/"},
            follow=True,
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("_auth_user_id", self.client.session)


@override_settings(SECURE_SSL_REDIRECT=False)
class RoleAssignmentConcurrencyTests(TransactionTestCase):
    def test_dos_guardados_concurrentes_dejan_un_solo_rol_educativo(self):
        administrator = User.objects.create_superuser("admin@colegio.example")
        target = User.objects.create_user("persona@colegio.example")
        roles = [Group.objects.get_or_create(name=name)[0] for name in ("estudiante", "docente")]
        url = reverse("admin:accounts_user_change", args=[target.pk])
        barrier = Barrier(2)

        def assign_role(role):
            try:
                client = Client()
                client.force_login(administrator)
                barrier.wait(timeout=10)
                return client.post(url, {"is_active": "on", "groups": [role.pk]}).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(list(executor.map(assign_role, roles)), [302, 302])
        self.assertEqual(target.groups.count(), 1)
        self.assertIn(target.groups.get(), roles)
