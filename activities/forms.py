import io
import warnings

from django import forms
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError

from .packages import inspect_package


class ActivityUploadForm(forms.Form):
    title = forms.CharField(label="Nombre", max_length=100)
    description = forms.CharField(label="Descripción breve", max_length=300, widget=forms.Textarea(attrs={"rows": 3}))
    image = forms.FileField(label="Imagen de portada", help_text="PNG, JPEG o WebP de hasta 8 MiB.", widget=forms.ClearableFileInput(attrs={"accept": "image/png,image/jpeg,image/webp"}))
    package = forms.FileField(label="Actividad de Godot", help_text="ZIP de la exportación Web completa, de un solo hilo y sin PWA. Hasta 150 MiB.", widget=forms.ClearableFileInput(attrs={"accept": ".zip"}))
    students = forms.ModelMultipleChoiceField(label="Alumnos autorizados", queryset=None, help_text="Selecciona los alumnos que podrán ver y abrir esta actividad.", widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["students"].queryset = get_user_model().objects.filter(
            is_active=True, groups__name="estudiante"
        ).exclude(groups__name="docente").order_by("email")

    def clean_package(self):
        upload = self.cleaned_data["package"]
        inspect_package(upload)
        return upload

    def clean_image(self):
        upload = self.cleaned_data["image"]
        if upload.size > 8 * 1024 * 1024:
            raise forms.ValidationError("La imagen supera 8 MiB.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(upload) as image:
                    if image.format not in {"PNG", "JPEG", "WEBP"} or image.width * image.height > 16_000_000:
                        raise forms.ValidationError("Usa una imagen PNG, JPEG o WebP de hasta 16 megapíxeles.")
                    image.load()
                    image.thumbnail((1200, 800))
                    output = io.BytesIO()
                    image.convert("RGB").save(output, format="PNG")
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError) as error:
            raise forms.ValidationError("No se pudo leer la imagen. Elige otra portada.") from error
        return ContentFile(output.getvalue(), name="cover.png")


class ActivityReviewForm(forms.Form):
    clarity = forms.BooleanField(label="Revisé que las instrucciones sean claras.")
    suitability = forms.BooleanField(label="Revisé la pertinencia pedagógica para los alumnos seleccionados.")
    distractions = forms.BooleanField(label="Revisé los distractores, sonidos y animaciones.")
