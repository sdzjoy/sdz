from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("studio", "0004_alter_auditevent_action"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditevent",
            name="action",
            field=models.CharField(
                choices=[
                    ("bulk_publish", "批量发布"),
                    ("bulk_unpublish", "批量取消发布"),
                    ("move_to_trash", "移入回收站"),
                    ("restore_from_trash", "移出回收站"),
                    ("permanent_delete", "永久删除"),
                    ("manual_save", "手工保存"),
                    ("publish", "发布内容"),
                    ("restore_revision", "恢复历史版本"),
                    ("asset_upload", "上传素材"),
                    ("asset_delete", "删除素材"),
                ],
                db_index=True,
                max_length=32,
                verbose_name="动作",
            ),
        ),
    ]
