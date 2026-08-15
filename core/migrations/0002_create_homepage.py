from django.db import migrations


HOME_TITLE = "少惰主"
HOME_SLUG = "home"


def _site_values(site):
    if site is None:
        return {
            "hostname": "localhost",
            "port": 80,
            "site_name": "少惰主 · SDZJOY",
            "is_default_site": True,
        }

    return {
        "hostname": site.hostname,
        "port": site.port,
        "site_name": site.site_name,
        "is_default_site": site.is_default_site,
    }


def create_homepage(apps, schema_editor):
    ContentType = apps.get_model("contenttypes.ContentType")
    HomePage = apps.get_model("core.HomePage")
    Locale = apps.get_model("wagtailcore.Locale")
    Page = apps.get_model("wagtailcore.Page")
    Site = apps.get_model("wagtailcore.Site")

    existing_site = Site.objects.filter(is_default_site=True).first()
    site_values = _site_values(existing_site)

    page_content_type = ContentType.objects.get(
        app_label="wagtailcore",
        model="page",
    )
    Page.objects.filter(
        content_type=page_content_type,
        slug=HOME_SLUG,
        depth=2,
    ).delete()

    homepage_content_type, _ = ContentType.objects.get_or_create(
        app_label="core",
        model="homepage",
    )
    homepage = HomePage.objects.create(
        title=HOME_TITLE,
        draft_title=HOME_TITLE,
        slug=HOME_SLUG,
        content_type=homepage_content_type,
        path="00010001",
        depth=2,
        numchild=0,
        url_path=f"/{HOME_SLUG}/",
        locale=Locale.objects.order_by("pk").first(),
        live=True,
    )

    Site.objects.update_or_create(
        hostname=site_values["hostname"],
        port=site_values["port"],
        defaults={
            "site_name": site_values["site_name"],
            "root_page": homepage,
            "is_default_site": site_values["is_default_site"],
        },
    )


def restore_wagtail_homepage(apps, schema_editor):
    ContentType = apps.get_model("contenttypes.ContentType")
    HomePage = apps.get_model("core.HomePage")
    Locale = apps.get_model("wagtailcore.Locale")
    Page = apps.get_model("wagtailcore.Page")
    Site = apps.get_model("wagtailcore.Site")

    existing_site = Site.objects.filter(is_default_site=True).first()
    site_values = _site_values(existing_site)
    HomePage.objects.filter(slug=HOME_SLUG, depth=2).delete()

    page_content_type = ContentType.objects.get(
        app_label="wagtailcore",
        model="page",
    )
    homepage = Page.objects.create(
        title="Welcome to your new Wagtail site!",
        draft_title="Welcome to your new Wagtail site!",
        slug=HOME_SLUG,
        content_type=page_content_type,
        path="00010001",
        depth=2,
        numchild=0,
        url_path=f"/{HOME_SLUG}/",
        locale=Locale.objects.order_by("pk").first(),
        live=True,
    )
    Site.objects.update_or_create(
        hostname=site_values["hostname"],
        port=site_values["port"],
        defaults={
            "site_name": site_values["site_name"],
            "root_page": homepage,
            "is_default_site": site_values["is_default_site"],
        },
    )
    ContentType.objects.filter(app_label="core", model="homepage").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_homepage, restore_wagtail_homepage),
    ]
