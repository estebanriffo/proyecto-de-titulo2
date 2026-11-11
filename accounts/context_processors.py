from django.conf import settings


def email_delivery(request):
    return {
        "email_to_console": settings.DEBUG
        and settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend",
    }
