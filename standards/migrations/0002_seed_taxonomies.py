from django.db import migrations


TERMS = (
    ("system", "规划、等级与总体要求", "planning_general", 10),
    ("system", "室内环境与室外条件", "indoor_outdoor", 20),
    ("system", "冷热源系统", "cooling_heating_source", 30),
    ("system", "空气系统", "air_system", 40),
    ("system", "水系统", "water_system", 50),
    ("system", "消防、防排烟与联动", "fire_smoke", 60),
    ("system", "自控与监测", "controls_monitoring", 70),
    ("system", "节能与能效评价", "energy_efficiency", 80),
    ("system", "施工、调试与验收", "construction_commissioning", 90),
    ("system", "运维与连续性", "operations_continuity", 100),
    ("design_stage", "规划与选址", "planning", 10),
    ("design_stage", "方案设计", "scheme", 20),
    ("design_stage", "施工图设计", "detailed_design", 30),
    ("design_stage", "施工与安装", "construction", 40),
    ("design_stage", "调试与验收", "commissioning", 50),
    ("design_stage", "运行与维护", "operations", 60),
    ("topic", "数据中心", "data_center", 10),
    ("topic", "供暖通风与空气调节", "hvac", 20),
    ("topic", "消防安全", "fire_safety", 30),
    ("topic", "自动化与监控", "automation", 40),
    ("topic", "能源与碳排放", "energy", 50),
    ("topic", "业务连续性", "continuity", 60),
    ("use_case", "新建", "new_build", 10),
    ("use_case", "改造", "retrofit", 20),
    ("use_case", "扩容", "expansion", 30),
    ("use_case", "运行维护", "operation_use", 40),
)


def seed_taxonomies(apps, schema_editor):
    term_model = apps.get_model("standards", "TaxonomyTerm")
    for kind, name, slug, sort_order in TERMS:
        term_model.objects.update_or_create(
            kind=kind,
            slug=slug,
            defaults={"name": name, "sort_order": sort_order},
        )


def remove_seeded_taxonomies(apps, schema_editor):
    term_model = apps.get_model("standards", "TaxonomyTerm")
    term_model.objects.filter(slug__in=[item[2] for item in TERMS]).delete()


class Migration(migrations.Migration):
    dependencies = [("standards", "0001_initial")]

    operations = [migrations.RunPython(seed_taxonomies, remove_seeded_taxonomies)]
