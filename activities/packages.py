import json
import re
import shutil
import stat
import tempfile
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Activity

MAX_UPLOAD = 150 * 1024 * 1024
MAX_EXPANDED = 300 * 1024 * 1024
ALLOWED_EXTENSIONS = {".html", ".js", ".wasm", ".pck", ".png", ".jpg", ".webp", ".ico", ".css"}


def inspect_package(upload):
    if not upload.name.lower().endswith(".zip"):
        raise ValidationError("Sube un ZIP exportado para Web desde Godot, con sus archivos HTML, JS, WASM y PCK.")
    if upload.size > MAX_UPLOAD:
        raise ValidationError("El ZIP supera el límite de 150 MiB.")
    try:
        with ZipFile(upload) as archive:
            files = [item for item in archive.infolist() if not item.is_dir()]
            if not files or len(files) > 300 or len(archive.infolist()) > 600:
                raise ValidationError("El paquete debe contener entre 1 y 300 archivos.")
            if sum(item.file_size for item in files) > MAX_EXPANDED:
                raise ValidationError("El paquete descomprimido supera 300 MiB.")
            names = set()
            for item in archive.infolist():
                path = PurePosixPath(item.filename)
                if (
                    path.is_absolute() or ".." in path.parts or "\\" in item.orig_filename
                    or ":" in item.orig_filename or "\x00" in item.orig_filename
                    or len(item.filename) > 220
                    or stat.S_ISLNK(item.external_attr >> 16) or item.flag_bits & 1
                ):
                    raise ValidationError("El ZIP contiene rutas o archivos no permitidos.")
                if item.is_dir():
                    continue
                if path.suffix.lower() not in ALLOWED_EXTENSIONS:
                    raise ValidationError("Solo se admiten archivos de una exportación Web de Godot. Exporta para Web y comprime el resultado completo.")
                normalized = str(path).casefold()
                if normalized in names:
                    raise ValidationError("El ZIP contiene nombres de archivo duplicados.")
                names.add(normalized)
                if item.file_size > 1024 * 1024 and item.file_size / max(item.compress_size, 1) > 500:
                    raise ValidationError("El ZIP tiene una compresión excesiva.")
            html_files = [item for item in files if item.filename.endswith(".html")]
            if len(html_files) != 1 or html_files[0].file_size > 1024 * 1024:
                raise ValidationError("El ZIP debe incluir un único HTML de inicio de Godot.")
            html_name = html_files[0].filename
            html = archive.read(html_name).decode("utf-8-sig")
            match = re.search(r"const\s+GODOT_CONFIG\s*=\s*(\{[^\n]*\})\s*;", html)
            if not match or "new Engine(" not in html:
                raise ValidationError("El HTML debe ser el generado por una exportación Web de Godot 4.")
            config = json.loads(match[1])
            executable = config.get("executable", "")
            if not isinstance(executable, str) or not re.fullmatch(r"[\w .-]+", executable) or executable in {".", ".."}:
                raise ValidationError("La exportación tiene un nombre de ejecutable no válido.")
            parent = PurePosixPath(html_name).parent
            for extension, signature in ((".js", None), (".wasm", b"\x00asm\x01\x00\x00\x00"), (".pck", b"GDPC")):
                name = str(parent / (executable + extension))
                if name not in archive.namelist():
                    raise ValidationError("Faltan archivos JS, WASM o PCK de la exportación. Incluye todos los archivos generados por Godot.")
                if signature:
                    with archive.open(name) as file:
                        if file.read(len(signature)) != signature:
                            raise ValidationError("El paquete contiene un archivo WASM o PCK no válido.")
            if config.get("gdextensionLibs") or any("service.worker" in item.filename for item in files):
                raise ValidationError("Exporta para Web con PWA y soporte de extensiones desactivados.")
            return html_name
    except (BadZipFile, KeyError, UnicodeError, ValueError, RuntimeError, OSError) as error:
        raise ValidationError("No se pudo leer el ZIP. Vuelve a exportar la actividad para Web.") from error
    finally:
        upload.seek(0)


def publish_activity(*, owner, title, description, students, package, image):
    entrypoint = inspect_package(package)
    activity = Activity(owner=owner, title=title, description=description, entrypoint=entrypoint)
    base = Path(settings.GODOT_ACTIVITIES_ROOT).resolve()
    base.mkdir(parents=True, exist_ok=True)
    destination = base / str(activity.pk)
    try:
        with tempfile.TemporaryDirectory(dir=base, prefix="upload-") as temporary:
            staging = Path(temporary) / "package"
            staging.mkdir()
            with ZipFile(package) as archive:
                for item in archive.infolist():
                    if item.is_dir():
                        continue
                    target = staging.joinpath(*PurePosixPath(item.filename).parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(item) as source, target.open("xb") as output:
                        shutil.copyfileobj(source, output)
            (Path(temporary) / "cover.png").write_bytes(image.read())
            with transaction.atomic():
                activity.save()
                activity.students.set(students)
                Path(temporary).rename(destination)
    except Exception:
        if destination.exists() and destination.resolve().is_relative_to(base):
            shutil.rmtree(destination)
        raise
    return activity
