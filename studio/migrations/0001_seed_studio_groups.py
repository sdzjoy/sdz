from django.db import migrations

GROUP_NAMES = ("studio-owner", "studio-editor", "studio-resource-admin")


def create_studio_groups(apps, schema_editor):
    group_model = apps.get_model("auth", "Group")
    for name in GROUP_NAMES:
        group_model.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    initial = True
    dependencies = [("auth", "0012_alter_user_first_name_max_length")]
    operations = [migrations.RunPython(create_studio_groups, migrations.RunPython.noop)]
