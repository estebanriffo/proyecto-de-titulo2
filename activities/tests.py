import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

from allauth.account.models import EmailAddress
from django.contrib.auth.models import Group
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, SimpleTestCase, override_settings
from django.urls import reverse
from PIL import Image

from accounts.models import User

from .models import Activity
from .packages import inspect_package, publish_activity
from .views import TOKEN_SALT


def web_package(extra=None):
    # Estructura mínima para probar la carga; no representa un motor Godot real.
    files = {
        "export/game.html": '<script src="game.js"></script><script>const GODOT_CONFIG = '
        + json.dumps({"executable": "game", "gdextensionLibs": []})
        + '; const engine = new Engine(GODOT_CONFIG);</script>',
        "export/game.js": "class Engine {}",
        "export/game.wasm": b"\x00asm\x01\x00\x00\x00",
        "export/game.pck": b"GDPCtest",
    }
    files.update(extra or {})
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        for name, contents in files.items():
            info = ZipInfo(name)
            info.filename = name
            archive.writestr(info, contents)
    data = output.getvalue()
    for name in files:
        if "\\" in name:
            data = data.replace(name.replace("\\", "/").encode(), name.encode())
    return SimpleUploadedFile("actividad.zip", data, content_type="application/zip")


def cover_image():
    output = io.BytesIO()
    Image.new("RGB", (24, 24), "#22635e").save(output, format="PNG")
    return SimpleUploadedFile("portada.png", output.getvalue(), content_type="image/png")


class PackageTests(SimpleTestCase):
    def test_exportacion_coherente_y_cursor_restaurado(self):
        package = web_package()
        self.assertEqual(inspect_package(package), "export/game.html")
        self.assertEqual(package.tell(), 0)

    def test_rechaza_ejecutables_rutas_externas_y_archivos_incompletos(self):
        for name in ("game.exe", "../escape.js", "/escape.js", "a\\escape.js", "a:escape.js"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                inspect_package(web_package({name: b"MZ"}))
        with self.assertRaises(ValidationError):
            inspect_package(web_package({"export/game.wasm": b"invalido"}))
        with self.assertRaises(ValidationError):
            inspect_package(SimpleUploadedFile("actividad.zip", b"invalido"))

    def test_rechaza_html_ajeno_archivos_duplicados_y_pwa(self):
        for extra in (
            {"export/game.html": "<h1>Pagina ajena</h1>"},
            {"export/GAME.js": b"duplicado"},
            {"export/game.service.worker.js": b"worker"},
        ):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                inspect_package(web_package(extra))


@override_settings(SECURE_SSL_REDIRECT=False)
class ActivityTests(TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        settings_override = override_settings(
            GODOT_ACTIVITIES_ROOT=Path(self.temporary.name) / "activities"
        )
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.teacher = self.make_user("teacher", "docente")
        self.student = self.make_user("student", "estudiante")
        self.other = self.make_user("other", "estudiante")
        self.activity = publish_activity(
            owner=self.teacher, title="Actividad de prueba", description="Descripción de prueba",
            students=[self.student], package=web_package(), image=cover_image(),
        )
        self.activity.is_active = True
        self.activity.save(update_fields=["is_active"])

    def make_user(self, name, role):
        user = User.objects.create_user(f"{name}@colegio.example")
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)
        EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
        return user

    def upload_data(self, package=None):
        return {
            "title": "Nueva actividad", "description": "Una actividad educativa.",
            "students": [self.student.pk], "package": package or web_package(),
            "image": cover_image(), "clarity": "on", "suitability": "on", "distractions": "on",
        }

    def test_docente_publica_por_formulario_y_alumno_ve_tarjeta_y_jugador(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse("activities:upload"), self.upload_data())
        self.assertEqual(response.status_code, 302)
        draft = Activity.objects.get(title="Nueva actividad")
        self.assertFalse(draft.is_active)
        response = self.client.post(response.url, {"clarity": "on", "suitability": "on", "distractions": "on"})
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.student)
        response = self.client.get(reverse("activities:list"))
        self.assertContains(response, "Nueva actividad")
        self.assertContains(response, reverse("activities:cover", args=[self.activity.pk]))
        response = self.client.get(reverse("activities:play", args=[self.activity.pk]))
        self.assertContains(response, 'sandbox="allow-scripts allow-pointer-lock"')
        self.assertNotContains(response, "allow-same-origin")
        cover = self.client.get(reverse("activities:cover", args=[self.activity.pk]))
        self.assertEqual(cover.status_code, 200)
        self.assertTrue(b"".join(cover.streaming_content).startswith(b"\x89PNG"))

    def test_visitante_y_alumno_ajeno_no_acceden(self):
        list_url = reverse("activities:list")
        self.assertEqual(self.client.get(list_url).status_code, 302)
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(list_url), self.activity.title)
        self.assertEqual(self.client.get(reverse("activities:play", args=[self.activity.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("activities:cover", args=[self.activity.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("activities:upload"), self.upload_data()).status_code, 403)

    def test_otro_docente_no_consulta_publicaciones_ajenas_y_admin_si(self):
        teacher = self.make_user("another-teacher", "docente")
        self.client.force_login(teacher)
        self.assertEqual(self.client.get(reverse("activities:play", args=[self.activity.pk])).status_code, 404)
        self.client.force_login(self.make_user("admin", "administrador"))
        self.assertEqual(self.client.get(reverse("activities:play", args=[self.activity.pk])).status_code, 200)

    def test_borrador_exige_revision_y_no_es_visible_para_alumnos(self):
        self.activity.is_active = False
        self.activity.save(update_fields=["is_active"])
        self.client.force_login(self.student)
        self.assertNotContains(self.client.get(reverse("activities:list")), self.activity.title)
        self.client.force_login(self.teacher)
        url = reverse("activities:play", args=[self.activity.pk])
        response = self.client.post(url, {"clarity": "on"})
        self.assertContains(response, "Este campo es obligatorio")
        self.activity.refresh_from_db()
        self.assertFalse(self.activity.is_active)

    def test_archivos_firmados_revocacion_y_recorrido_de_rutas(self):
        token = signing.dumps({"activity": str(self.activity.pk), "user": self.student.pk}, salt=TOKEN_SALT)
        url = reverse("activities:asset", kwargs={"token": token, "filename": self.activity.entrypoint})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], "*")
        self.assertIn("sandbox allow-scripts", response["Content-Security-Policy"])
        self.assertEqual(response["X-Frame-Options"], "SAMEORIGIN")
        self.assertIn(b"GODOT_CONFIG", response.content)
        traversal = reverse("activities:asset", kwargs={"token": token, "filename": "../cover.png"})
        self.assertEqual(self.client.get(traversal).status_code, 404)
        self.activity.students.clear()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_puente_de_audio_autorizado_y_aislado(self):
        token = signing.dumps({"activity": str(self.activity.pk), "user": self.student.pk}, salt=TOKEN_SALT)
        html_url = reverse("activities:asset", kwargs={"token": token, "filename": self.activity.entrypoint})
        bridge_url = reverse("activities:asset", kwargs={"token": token, "filename": "__aamr_audio_bridge.js"})
        # El HTML de esta prueba usa una cabecera completa como las exportaciones reales.
        package_path = Path(self.temporary.name, "activities", str(self.activity.pk), "package", self.activity.entrypoint)
        package_path.write_text("<html><head></head><body>Prueba</body></html>", encoding="utf-8")
        self.assertContains(self.client.get(html_url), "__aamr_audio_bridge.js")
        response = self.client.get(bridge_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"aamr:set-volume", b"".join(response.streaming_content))
        self.activity.students.clear()
        self.assertEqual(self.client.get(bridge_url).status_code, 404)

    def test_token_caducado_y_cuenta_desactivada(self):
        with patch("django.core.signing.time.time", return_value=1):
            expired = signing.dumps({"activity": str(self.activity.pk), "user": self.student.pk}, salt=TOKEN_SALT)
        token = signing.dumps({"activity": str(self.activity.pk), "user": self.student.pk}, salt=TOKEN_SALT)
        self.student.is_active = False
        self.student.save(update_fields=["is_active"])
        for value in (expired, token, "invalido"):
            url = reverse("activities:asset", kwargs={"token": value, "filename": self.activity.entrypoint})
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_zip_windows_y_portada_invalida_no_crean_registros_ni_archivos(self):
        self.client.force_login(self.teacher)
        before = set(Path(self.temporary.name, "activities").iterdir())
        response = self.client.post(reverse("activities:upload"), self.upload_data(web_package({"reactors.exe": b"MZ"})))
        self.assertContains(response, "Exporta para Web")
        data = self.upload_data()
        data["image"] = SimpleUploadedFile("portada.png", b"imagen falsa")
        response = self.client.post(reverse("activities:upload"), data)
        self.assertContains(response, "No se pudo leer la imagen")
        self.assertEqual(Activity.objects.count(), 1)
        self.assertEqual(set(Path(self.temporary.name, "activities").iterdir()), before)

    def test_fallo_de_persistencia_limpia_la_carga(self):
        before = set(Path(self.temporary.name, "activities").iterdir())
        with patch.object(Activity, "save", side_effect=RuntimeError("fallo")):
            with self.assertRaises(RuntimeError):
                publish_activity(owner=self.teacher, title="Fallo", description="Prueba", students=[self.student], package=web_package(), image=cover_image())
        self.assertEqual(set(Path(self.temporary.name, "activities").iterdir()), before)
