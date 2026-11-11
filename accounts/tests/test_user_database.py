from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import authenticate
from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, connections, transaction
from django.test import TestCase, TransactionTestCase

from accounts.models import User


class UserDatabaseTests(TestCase):
    def test_normaliza_el_correo_al_crear_y_guardar(self):
        user = User.objects.create_user("  Estudiante@Colegio.EXAMPLE  ")
        user.refresh_from_db()
        self.assertEqual(user.email, "estudiante@colegio.example")

        user.email = "  Otro@Colegio.EXAMPLE  "
        user.save(update_fields=["email"])
        user.refresh_from_db()
        self.assertEqual(user.email, "otro@colegio.example")

    def test_base_rechaza_mayusculas_duplicadas_al_omitir_save(self):
        User.objects.create_user("estudiante@colegio.example")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.bulk_create([User(email="ESTUDIANTE@COLEGIO.EXAMPLE")])

    def test_base_rechaza_espacios_exteriores_al_omitir_save(self):
        for email in (
            " estudiante@colegio.example",
            "estudiante@colegio.example ",
            "\testudiante@colegio.example",
            "estudiante@colegio.example\n",
        ):
            with self.subTest(email=email):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    User.objects.bulk_create([User(email=email)])

    def test_actualizacion_directa_tambien_respeta_unicidad(self):
        User.objects.create_user("primero@colegio.example")
        second = User.objects.create_user("segundo@colegio.example")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=second.pk).update(email="PRIMERO@COLEGIO.EXAMPLE")

    def test_createsuperuser_funciona_con_correo_y_contrasena(self):
        password = "Clave-ficticia-para-pruebas-2026"
        with patch.dict("os.environ", {"DJANGO_SUPERUSER_PASSWORD": password}):
            call_command(
                "createsuperuser",
                email="Admin@Colegio.EXAMPLE",
                interactive=False,
                stdout=StringIO(),
            )
        user = User.objects.get(email="admin@colegio.example")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password(password))
        self.assertEqual(
            authenticate(email=user.email, password=password).pk,
            user.pk,
        )


class UserUniquenessConcurrencyTests(TransactionTestCase):
    def test_dos_creaciones_concurrentes_generan_una_sola_cuenta(self):
        barrier = Barrier(2)

        def create_user(email):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                with transaction.atomic():
                    User.objects.bulk_create([User(email=email)])
                return "creada"
            except IntegrityError:
                return "duplicada"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    create_user,
                    ["estudiante@colegio.example", "ESTUDIANTE@COLEGIO.EXAMPLE"],
                )
            )

        self.assertCountEqual(results, ["creada", "duplicada"])
        self.assertEqual(User.objects.count(), 1)
