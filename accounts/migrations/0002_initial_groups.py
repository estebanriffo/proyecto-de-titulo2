from django.db import migrations


def create_groups(apps, schema_editor):
    database = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    for name in ("estudiante", "docente", "administrador"):
        Group.objects.using(database).get_or_create(name=name)

    # post_migrate aún no creó los permisos en una base vacía.
    content_type, _ = ContentType.objects.using(database).get_or_create(
        app_label="accounts", model="user"
    )
    administrator = Group.objects.using(database).get(name="administrador")
    for action in ("view", "change"):
        permission, _ = Permission.objects.using(database).get_or_create(
            content_type=content_type,
            codename=f"{action}_user",
            defaults={"name": f"Can {action} user"},
        )
        administrator.permissions.add(permission)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        # Conservar las asignaciones si se revierte el esquema.
        migrations.RunPython(create_groups, migrations.RunPython.noop),
    ]
