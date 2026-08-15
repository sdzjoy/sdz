from wagtail.models import Page


class HomePage(Page):
    max_count = 1
    parent_page_types = ["wagtailcore.Page"]
    subpage_types = [
        "content.ProjectIndexPage",
        "content.ArticleIndexPage",
        "content.NoteIndexPage",
        "content.ToolIndexPage",
        "content.AboutPage",
    ]

    class Meta:
        verbose_name = "首页"

    def get_context(self, request, *args, **kwargs):
        from content.models import ArticlePage, NotePage, ProjectPage, ToolPage

        context = super().get_context(request, *args, **kwargs)
        public_projects = ProjectPage.objects.live().public()
        context.update(
            {
                "current_projects": public_projects.filter(
                    status__in=[ProjectPage.Status.ACTIVE, ProjectPage.Status.MAINTAINED]
                ).order_by("-featured", "-started_on")[:3],
                "completed_projects": public_projects.filter(
                    status=ProjectPage.Status.COMPLETE
                ).order_by("-featured", "-completed_on", "-started_on")[:3],
                "latest_articles": ArticlePage.objects.live()
                .public()
                .order_by("-published_on", "-first_published_at")[:3],
                "latest_notes": NotePage.objects.live()
                .public()
                .order_by("-noted_on", "-first_published_at")[:4],
                "featured_tools": ToolPage.objects.live()
                .public()
                .order_by("-featured", "-launched_on")[:3],
            }
        )
        context["has_public_content"] = any(
            context[key]
            for key in (
                "current_projects",
                "completed_projects",
                "latest_articles",
                "latest_notes",
                "featured_tools",
            )
        )
        return context
