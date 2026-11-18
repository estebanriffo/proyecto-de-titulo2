import mimetypes
import re
from html import escape
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile

from allauth.account.decorators import verified_email_required
from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from .access import can_publish, is_student, visible_activities
from .forms import ActivityReviewForm, ActivityUploadForm
from .models import Activity
from .packages import ALLOWED_EXTENSIONS, publish_activity

TOKEN_SALT = "activities.web-package"
AUDIO_BRIDGE_NAME = "__aamr_audio_bridge.js"


@never_cache
@require_safe
@verified_email_required
def activity_list(request):
    if not is_student(request.user):
        raise PermissionDenied
    return render(request, "activities/list.html", {"activities": visible_activities(request.user)})


@never_cache
@require_safe
@verified_email_required
def manage(request):
    if not can_publish(request.user):
        raise PermissionDenied
    return render(request, "activities/manage.html", {"activities": visible_activities(request.user)})


@never_cache
@require_http_methods(["GET", "POST"])
@verified_email_required
def upload(request):
    if not can_publish(request.user):
        raise PermissionDenied
    form = ActivityUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            activity = publish_activity(
                owner=request.user, title=data["title"], description=data["description"],
                students=data["students"], package=data["package"], image=data["image"],
            )
        except ValidationError as error:
            form.add_error("package", error)
        except (OSError, BadZipFile):
            form.add_error(None, "No se pudo guardar la actividad. Vuelve a seleccionar los archivos e inténtalo otra vez.")
        else:
            messages.success(request, "Actividad guardada. Pruébala y completa la revisión para publicarla.")
            return redirect("activities:play", pk=activity.pk)
    return render(request, "activities/upload.html", {"form": form})


@never_cache
@require_http_methods(["GET", "POST"])
@verified_email_required
def play(request, pk):
    activity = get_object_or_404(visible_activities(request.user), pk=pk)
    review_form = ActivityReviewForm(request.POST or None)
    if request.method == "POST":
        if not can_publish(request.user):
            raise PermissionDenied
        if review_form.is_valid():
            activity.is_active = True
            activity.save(update_fields=["is_active"])
            messages.success(request, "Actividad publicada para los alumnos seleccionados.")
            return redirect("activities:play", pk=activity.pk)
    token = signing.dumps({"activity": str(activity.pk), "user": request.user.pk}, salt=TOKEN_SALT)
    return render(request, "activities/play.html", {
        "activity": activity,
        "review_form": review_form,
        "can_publish_activity": can_publish(request.user),
        "game_url": reverse("activities:asset", kwargs={"token": token, "filename": activity.entrypoint}),
    })


@never_cache
@require_safe
@verified_email_required
def cover(request, pk):
    activity = get_object_or_404(visible_activities(request.user), pk=pk)
    path = Path(settings.GODOT_ACTIVITIES_ROOT) / str(activity.pk) / "cover.png"
    try:
        return FileResponse(path.open("rb"), content_type="image/png")
    except FileNotFoundError:
        raise Http404 from None


@never_cache
@require_safe
def asset(request, token, filename):
    # El iframe tiene un origen opaco y descarga los archivos sin cookies.
    # El enlace firmado identifica al usuario; sus permisos se vuelven a consultar.
    try:
        payload = signing.loads(token, salt=TOKEN_SALT, max_age=7200)
        user = get_user_model().objects.get(pk=payload["user"], is_active=True)
        if not EmailAddress.objects.filter(user=user, verified=True, primary=True).exists():
            raise PermissionDenied
        activity = get_object_or_404(visible_activities(user), pk=payload["activity"])
    except (signing.BadSignature, KeyError, ValueError, get_user_model().DoesNotExist):
        raise Http404 from None
    root = Path(settings.GODOT_ACTIVITIES_ROOT).resolve() / str(activity.pk) / "package"
    path = (root / filename).resolve()
    if (
        not path.is_relative_to(root) or path.suffix.lower() not in ALLOWED_EXTENSIONS
        or (path.suffix.lower() == ".html" and PurePosixPath(filename) != PurePosixPath(activity.entrypoint))
    ):
        raise Http404
    bridge_url = reverse("activities:asset", kwargs={"token": token, "filename": AUDIO_BRIDGE_NAME})
    try:
        if filename == AUDIO_BRIDGE_NAME:
            bridge_path = Path(__file__).resolve().parent / "static" / "activities" / "audio-bridge.js"
            response = FileResponse(bridge_path.open("rb"), content_type="text/javascript")
        elif path.suffix.lower() == ".html":
            html = path.read_text(encoding="utf-8-sig")
            script = f'<script src="{escape(bridge_url, quote=True)}"></script>'
            html, count = re.subn(r"(<head\b[^>]*>)", lambda match: match[0] + script, html, count=1, flags=re.IGNORECASE)
            if not count:
                html = script + html
            response = HttpResponse(html, content_type="text/html; charset=utf-8")
        else:
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            response = FileResponse(path.open("rb"), content_type=content_type)
    except (OSError, ValueError):
        raise Http404 from None
    package_url = request.build_absolute_uri(reverse("activities:asset", kwargs={"token": token, "filename": activity.entrypoint}))
    package_source = package_url.rsplit("/", 1)[0] + "/"
    response["Access-Control-Allow-Origin"] = "*"
    response["Cross-Origin-Resource-Policy"] = "cross-origin"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Frame-Options"] = "SAMEORIGIN"
    response["Content-Security-Policy"] = (
        "sandbox allow-scripts allow-pointer-lock; default-src 'none'; "
        f"script-src {package_source} {request.build_absolute_uri(bridge_url)} 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval'; "
        f"connect-src {package_source}; img-src {package_source} data: blob:; "
        "style-src 'unsafe-inline'; worker-src blob:; media-src blob:; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
    )
    return response
