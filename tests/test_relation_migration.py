from datetime import date
from importlib import import_module

import pytest
from django.apps import apps
from django.db import connection

from accounts.models import User
from publishing.models import Article, Tool
from standards.models import Standard

pytestmark = pytest.mark.django_db(transaction=True)
PASSWORD = "a-safe-test-password"  # noqa: S105


def test_existing_standard_links_are_repointed_without_losing_rows():
    actor = User.objects.create_user("relation-migration@example.com", PASSWORD)
    article = Article.objects.create(
        legacy_source_id=81001,
        title="关系迁移文章",
        slug="relation-article",
        author=actor,
        published_on=date(2026, 8, 17),
    )
    tool = Tool.objects.create(
        legacy_source_id=82001,
        title="关系迁移工具",
        slug="relation-tool",
        author=actor,
        launched_on=date(2026, 8, 17),
    )
    standard = Standard.objects.create(
        code="GB TEST-RELATION",
        slug="gb-test-relation",
        title_cn="关联迁移测试",
        category=Standard.Category.NATIONAL,
    )

    conversion = import_module("standards.migrations.0004_repoint_content_relations")
    quote = connection.ops.quote_name
    relation_rows = (
        (
            "standards_standard_related_articles",
            "article_id",
            "articlepage_id",
            article.legacy_source_id,
        ),
        (
            "standards_standard_related_tools",
            "tool_id",
            "toolpage_id",
            tool.legacy_source_id,
        ),
    )

    connection.disable_constraint_checking()
    try:
        with connection.cursor() as cursor:
            for table, current_column, retired_column, source_id in relation_rows:
                cursor.execute(
                    f"ALTER TABLE {quote(table)} RENAME COLUMN "
                    f"{quote(current_column)} TO {quote(retired_column)}"
                )
                cursor.execute(
                    f"INSERT INTO {quote(table)} (standard_id, {quote(retired_column)}) "  # noqa: S608
                    "VALUES (%s, %s)",
                    [standard.pk, source_id],
                )
        with connection.schema_editor() as schema_editor:
            conversion.create_or_repoint_relations(apps, schema_editor)
    finally:
        connection.enable_constraint_checking()

    standard.refresh_from_db()
    assert list(standard.related_articles.all()) == [article]
    assert list(standard.related_tools.all()) == [tool]
