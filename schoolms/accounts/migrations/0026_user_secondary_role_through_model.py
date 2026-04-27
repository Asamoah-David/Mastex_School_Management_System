from django.db import migrations, models
import django.db.models.deletion


def _backfill_secondary_roles(apps, schema_editor):
    """Parse existing secondary_roles CSV on each User → create UserSecondaryRole rows."""
    User = apps.get_model("accounts", "User")
    UserSecondaryRole = apps.get_model("accounts", "UserSecondaryRole")

    to_create = []
    for user in User.objects.exclude(secondary_roles="").only("pk", "role", "secondary_roles"):
        raw = [r.strip() for r in (user.secondary_roles or "").split(",") if r.strip()]
        seen = set()
        for role in raw:
            if role == user.role or role in seen:
                continue
            seen.add(role)
            to_create.append(UserSecondaryRole(user_id=user.pk, role=role))

        if len(to_create) >= 500:
            UserSecondaryRole.objects.bulk_create(to_create, ignore_conflicts=True)
            to_create = []

    if to_create:
        UserSecondaryRole.objects.bulk_create(to_create, ignore_conflicts=True)


class Migration(migrations.Migration):
    """ARCH-5: Replace secondary_roles TextField with UserSecondaryRole through-model.

    1. CreateModel UserSecondaryRole
    2. RunPython: back-fill rows from the existing CSV field
    3. RemoveField User.secondary_roles
    """

    dependencies = [
        ("accounts", "0025_staffperformancereview"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserSecondaryRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(
                    choices=[
                        ("super_admin", "Super Admin"),
                        ("school_admin", "Headteacher/Admin"),
                        ("deputy_head", "Deputy Headteacher"),
                        ("hod", "Head of Department"),
                        ("teacher", "Teacher"),
                        ("accountant", "Accountant/Bursar"),
                        ("librarian", "Librarian"),
                        ("admission_officer", "Admission Officer"),
                        ("school_nurse", "School Nurse"),
                        ("admin_assistant", "Admin Assistant"),
                        ("staff", "Staff"),
                        ("student", "Student"),
                        ("parent", "Parent"),
                    ],
                    db_index=True,
                    max_length=30,
                )),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="secondary_role_entries",
                        to="accounts.user",
                    ),
                ),
            ],
            options={
                "verbose_name": "User Secondary Role",
                "verbose_name_plural": "User Secondary Roles",
                "unique_together": {("user", "role")},
            },
        ),
        migrations.AddIndex(
            model_name="usersecondaryRole",
            index=models.Index(fields=["user", "role"], name="idx_user_secondary_role"),
        ),
        migrations.RunPython(
            _backfill_secondary_roles,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="user",
            name="secondary_roles",
        ),
    ]
