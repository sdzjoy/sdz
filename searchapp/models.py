from django.db import models


class SearchDocument(models.Model):
    class Kind(models.TextChoices):
        PROJECT = "project", "项目"
        ARTICLE = "article", "文章"
        NOTE = "note", "随记"
        STANDARD = "standard", "规范"
        RESOURCE = "resource", "资源"
        TOOL = "tool", "工具"

    kind = models.CharField("内容类型", max_length=16, choices=Kind.choices, db_index=True)
    object_id = models.CharField("对象标识", max_length=64)
    title = models.CharField("标题", max_length=500)
    summary = models.TextField("摘要", blank=True)
    search_text = models.TextField("检索文本", blank=True)
    url = models.CharField("站内地址", max_length=500)
    access_level = models.CharField("最低等级", max_length=2, default="L0", db_index=True)
    source_updated_at = models.DateTimeField("来源更新时间", null=True, blank=True)
    indexed_at = models.DateTimeField("索引时间", auto_now=True)

    class Meta:
        ordering = ("kind", "title")
        verbose_name = "搜索记录"
        verbose_name_plural = "搜索记录"
        constraints = [
            models.UniqueConstraint(
                fields=("kind", "object_id"), name="unique_search_document_source"
            )
        ]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.title}"

