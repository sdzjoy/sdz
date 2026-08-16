# ruff: noqa: S608 -- table and column names are fixed constants and backend-quoted
from django.db import migrations, models

RELATIONS = (
    {
        "field": "related_articles",
        "legacy_table": "standards_standard_related_articles",
        "target_table": "standards_standard_publishing_articles",
        "old_column": "articlepage_id",
        "new_column": "article_id",
        "kind": "article",
    },
    {
        "field": "related_tools",
        "legacy_table": "standards_standard_related_tools",
        "target_table": "standards_standard_publishing_tools",
        "old_column": "toolpage_id",
        "new_column": "tool_id",
        "kind": "tool",
    },
)


def _columns(connection, cursor, table):
    return {column.name for column in connection.introspection.get_table_description(cursor, table)}


def create_or_repoint_relations(apps, schema_editor):
    from standards.models import Standard

    connection = schema_editor.connection
    quote = schema_editor.quote_name
    existing_tables = set(connection.introspection.table_names())

    with connection.cursor() as cursor:
        for relation in RELATIONS:
            through = Standard._meta.get_field(relation["field"]).remote_field.through
            if relation["target_table"] not in existing_tables:
                schema_editor.create_model(through)
                existing_tables.add(relation["target_table"])

            if relation["legacy_table"] not in existing_tables:
                continue

            columns = _columns(connection, cursor, relation["legacy_table"])
            if relation["old_column"] not in columns:
                raise RuntimeError(f"{relation['legacy_table']} 的旧关系列无法识别；已停止迁移。")

            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM {quote(relation["legacy_table"])} AS legacy
                LEFT JOIN publishing_contententry AS entry
                  ON entry.legacy_source_id = legacy.{quote(relation["old_column"])}
                 AND entry.kind = %s
                WHERE entry.id IS NULL
                """,
                [relation["kind"]],
            )
            missing = cursor.fetchone()[0]
            if missing:
                raise RuntimeError(
                    f"{relation['legacy_table']} 有 {missing} 条关系找不到已转换内容；已停止迁移。"
                )

            cursor.execute(
                f"""
                INSERT INTO {quote(relation["target_table"])}
                    (standard_id, {quote(relation["new_column"])})
                SELECT legacy.standard_id AS standard_id, entry.id AS target_id
                FROM {quote(relation["legacy_table"])} AS legacy
                JOIN publishing_contententry AS entry
                  ON entry.legacy_source_id = legacy.{quote(relation["old_column"])}
                 AND entry.kind = %s
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM {quote(relation["target_table"])} AS target
                    WHERE target.standard_id = legacy.standard_id
                      AND target.{quote(relation["new_column"])} = entry.id
                )
                """,
                [relation["kind"]],
            )


class Migration(migrations.Migration):
    dependencies = [
        ("publishing", "0002_legacy_source_ids"),
        ("standards", "0003_monitoringsource_candidatechange_candidatereview_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="standard",
                    name="related_articles",
                    field=models.ManyToManyField(
                        blank=True,
                        db_table="standards_standard_publishing_articles",
                        related_name="related_standards",
                        to="publishing.article",
                        verbose_name="相关文章",
                    ),
                ),
                migrations.AddField(
                    model_name="standard",
                    name="related_tools",
                    field=models.ManyToManyField(
                        blank=True,
                        db_table="standards_standard_publishing_tools",
                        related_name="related_standards",
                        to="publishing.tool",
                        verbose_name="相关工具",
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(
                    create_or_repoint_relations,
                    migrations.RunPython.noop,
                )
            ],
        )
    ]
