from wagtail.models import Page


class HomePage(Page):
    max_count = 1
    parent_page_types = ["wagtailcore.Page"]
    subpage_types = []

    class Meta:
        verbose_name = "首页"
