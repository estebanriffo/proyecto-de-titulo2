from getpass import getpass

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from accounts.access import ROLE_NAMES
from accounts.models import User

DEMO_ACCOUNTS = (
    ("estudiante@aprendo.example", "estudiante"),
    ("docente@aprendo.example", "docente"),
    ("administrador@aprendo.example", "administrador"),
    ("pendiente@aprendo.example", None),
)


class Command(BaseCommand):
    help = "Crea cuatro cuentas ficticias para probar los accesos con DEBUG=True."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Este comando requiere DEBUG=True.")
        groups = {group.name: group for group in Group.objects.filter(name__in=ROLE_NAMES)}
        if set(groups) != set(ROLE_NAMES):
            raise CommandError("Ejecuta migrate para crear los tres grupos primero.")

        demo_emails = [email for email, _ in DEMO_ACCOUNTS]
        existing = set(
            User.objects.filter(email__in=demo_emails).values_list("email", flat=True)
        )
        pending = [(email, role) for email, role in DEMO_ACCOUNTS if email not in existing]
        if not pending:
            self.stdout.write("Las cuatro cuentas ficticias ya existen.")
            return

        password = getpass("Contraseña para las nuevas cuentas ficticias: ")
        if password != getpass("Repite la contraseña: "):
            raise CommandError("Las contraseñas deben coincidir.")
        try:
            for email, _ in pending:
                validate_password(password, user=User(email=email))
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from None

        try:
            with transaction.atomic():
                for email, role in pending:
                    user = User.objects.create_user(email, password)
                    EmailAddress.objects.create(
                        user=user, email=email, primary=True, verified=True
                    )
                    if role:
                        user.groups.add(groups[role])
        except IntegrityError:
            raise CommandError(
                "Otra operación creó una de las cuentas. Ejecuta el comando nuevamente."
            ) from None

        for email, role in pending:
            self.stdout.write(f"Creada {email} — {role or 'sin grupo'}")
        self.stdout.write(self.style.SUCCESS("Cuentas ficticias listas para iniciar sesión."))
