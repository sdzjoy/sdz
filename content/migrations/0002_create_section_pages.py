from django.db import migrations


SECTIONS = (
    ("projectindexpage", "ProjectIndexPage", "项目", "projects", "持续记录工程实践与长期项目。", "project"),
    ("articleindexpage", "ArticleIndexPage", "文章", "articles", "经过整理和验证的技术文章。", "article"),
    ("noteindexpage", "NoteIndexPage", "随记", "notes", "现场片段、实验记录与阶段性判断。", "note"),
    ("toolindexpage", "ToolIndexPage", "工具", "tools", "面向工程工作的查询工具与小型服务。", "tool"),
    ("aboutpage", "AboutPage", "关于", "about", "少惰主的工程背景、关注方向与联系方式。", "about"),
)


def _next_path(Page, parent):
    step = parent.numchild + 1
    while True:
        path = f"{parent.path}{step:04d}"
        if not Page.objects.filter(path=path).exists():
            return path
        step += 1


def create_section_pages(apps, schema_editor):
    ContentType = apps.get_model("contenttypes.ContentType")
    HomePage = apps.get_model("core.HomePage")
    Page = apps.get_model("wagtailcore.Page")

    home = HomePage.objects.filter(depth=2, slug="home").first()
    if home is None:
        return

    for model_name, class_name, title, slug, intro, _key in SECTIONS:
        if Page.objects.filter(depth=home.depth + 1, slug=slug).exists():
            continue

        model = apps.get_model("content", class_name)
        content_type, _ = ContentType.objects.get_or_create(
            app_label="content",
            model=model_name,
        )
        model.objects.create(
            title=title,
            draft_title=title,
            slug=slug,
            content_type=content_type,
            path=_next_path(Page, home),
            depth=home.depth + 1,
            numchild=0,
            url_path=f"{home.url_path}{slug}/",
            locale=home.locale,
            live=True,
            show_in_menus=True,
            intro=intro,
        )
        home.numchild = Page.objects.filter(depth=home.depth + 1).count()
        home.save(update_fields=["numchild"])


def remove_section_pages(apps, schema_editor):
    HomePage = apps.get_model("core.HomePage")
    Page = apps.get_model("wagtailcore.Page")

    home = HomePage.objects.filter(depth=2, slug="home").first()
    if home is None:
        return

    for model_name, _class_name, _title, slug, _intro, _key in SECTIONS:
        Page.objects.filter(
            depth=home.depth + 1,
            slug=slug,
            content_type__app_label="content",
            content_type__model=model_name,
        ).delete()
    home.numchild = Page.objects.filter(depth=home.depth + 1).count()
    home.save(update_fields=["numchild"])


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0001_initial"),
        ("core", "0002_create_homepage"),
    ]

    operations = [
        migrations.RunPython(create_section_pages, remove_section_pages),
    ]
