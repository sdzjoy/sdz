# 少惰主 CMS 内容工作台实施计划

- 设计依据：`docs/plans/2026-08-16--cms-editorial-workbench-redesign.md`
- 实施分支：`feat/platform-foundation`
- 实施原则：旧正文 JSON 不重写；数据库变更可回退；每批独立测试和提交；部署前先备份生产数据与媒体

## 第一批：专业写作数据底座

### 任务 1：公式渲染依赖与回归测试骨架

**文件**

- 修改：`requirements/base.txt`
- 新增：`tests/test_editorial_blocks.py`

**步骤**

1. 锁定纯 Python 的 `latex2mathml` 版本，用于服务端生成自托管 MathML。
2. 先写块定义、正常公式、异常公式、安全输出和旧块兼容测试。
3. 在本地虚拟环境安装新增依赖。
4. 运行新增测试，确认测试在功能实现前按预期失败，而不是测试本身无法收集。

**验证**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_editorial_blocks.py -q
```

### 任务 2：专业内容块与前台模板

**文件**

- 修改：`content/blocks.py`
- 修改：`content/templatetags/content_tags.py`
- 修改：`content/templates/content/blocks/code_block.html`
- 新增：`content/templates/content/blocks/callout_block.html`
- 新增：`content/templates/content/blocks/equation_block.html`
- 新增：`content/templates/content/blocks/reference_block.html`
- 新增：`content/templates/content/blocks/captioned_image_block.html`
- 新增：`content/templates/content/blocks/data_table_block.html`
- 新增：`content/templates/content/blocks/parameter_card_block.html`
- 新增：`content/templates/content/blocks/attachment_block.html`
- 新增：`content/templates/content/blocks/divider_block.html`

**步骤**

1. 按文字内容、工程资料、媒体附件和技术内容为块选择器分组。
2. 保留 `heading`、`paragraph`、`markdown`、`code`、`image`、`table` 的块名。
3. 新增提示框、工程公式、资料引用、图注图片、数据表、参数卡、附件和分隔线。
4. 公式由服务端转换成 MathML；转换失败时显示已转义的原始 LaTeX，不使整篇文章报错。
5. 扩展代码块的行号选项并保持旧 JSON 缺省值可加载。
6. 运行专业块测试和既有内容测试。

**验证**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_editorial_blocks.py tests\test_content.py -q
```

### 任务 3：文章模型、编辑面板与兼容迁移

**文件**

- 修改：`content/models.py`
- 新增：`content/migrations/0008_article_editorial_fields.py`（编号以实际迁移序列为准）
- 修改：`content/templates/content/article_page.html`
- 修改：`tests/test_content.py`

**步骤**

1. 为文章增加可空封面图，不改动已有文章。
2. 将阅读时间改为可选人工覆盖，并增加稳定的自动估算属性。
3. 增加结构化引用汇总与去重属性，供文章末尾参考资料使用。
4. 将标题、摘要、封面和正文放在主要写作区；文章日期、项目、主题、推荐和阅读时间放入文章资料/设置区。
5. 生成迁移，检查迁移文件不包含正文 JSON 重写。
6. 增加自动阅读时间、人工覆盖、引用去重、封面和旧正文兼容测试。

**验证**

```powershell
.\.venv\Scripts\python.exe manage.py makemigrations --check
.\.venv\Scripts\python.exe manage.py migrate --plan
.\.venv\Scripts\python.exe -m pytest tests\test_content.py tests\test_editorial_blocks.py -q
```

## 第二批：CMS 工作台与沉浸式编辑器

### 任务 4：内容工作台首页

**文件**

- 修改：`content/wagtail_hooks.py`
- 新增：`content/cms_components.py`
- 新增：`content/templates/wagtailadmin/home/editorial_workbench.html`
- 修改：`tests/test_admin.py`

**步骤**

1. 使用 Wagtail 首页组件加入新建文章、最近草稿、最近发布、内容数量和待整理随记。
2. 所有查询按当前用户页面权限过滤。
3. 操作入口复用 Wagtail 的新建、编辑和前台查看路由。
4. 验证普通后台用户看不到无权限操作。

### 任务 5：文章列表增强

**文件**

- 修改：`content/wagtail_hooks.py`
- 修改：`tests/test_admin.py`

**步骤**

1. 增加状态、项目、主题、阅读时间、推荐和最后修改列。
2. 增加标题搜索及状态、项目、主题、日期、推荐筛选。
3. 保持列表查询数量可控，避免逐行额外查询。
4. 验证标题入口直接进入编辑页。

### 任务 6：沉浸式编辑界面与公式即时预览

**文件**

- 修改：`content/wagtail_hooks.py`
- 新增：`content/admin_views.py`
- 新增：`content/templates/wagtailadmin/editorial/math_preview_error.html`
- 修改：`static/css/admin.css`
- 新增：`static/js/editorial-admin.js`
- 修改：`tests/test_admin.py`

**步骤**

1. 为文章编辑页增加沉浸式宽度、可收起资料区和清晰的保存/预览/发布层级。
2. 注册仅后台授权用户可访问的公式预览接口。
3. 预览请求做长度限制、节流和错误降级，不抓取外部资源。
4. 增加保存中、已保存、失败、未保存修改和离开提示；支持 `Ctrl+S`。
5. 保留 Wagtail 原有键盘和无障碍行为。

## 第三批：粘贴、前台表现与完整验收

### 任务 7：Word/网页/微信粘贴清理

**文件**

- 修改：`static/js/editorial-admin.js`
- 修改：`tests/test_admin.py`

**步骤**

1. 使用 DOM 白名单保留段落、标题、强调、列表、引用、链接和简单表格。
2. 删除来源样式、脚本、隐藏节点、Office 私有标记和空段落。
3. 对外部图片给出重新上传提示，不静默保存临时地址。
4. 清理失败时退回安全纯文本或默认粘贴。

### 任务 8：文章前台专业排版

**文件**

- 修改：`content/templates/content/article_page.html`
- 修改：`static/css/editorial.css`
- 修改：`tests/test_content.py`

**步骤**

1. 渲染封面、专业内容块和去重后的参考资料清单。
2. 为公式、表格、参数卡、提示框、图注和附件增加响应式样式。
3. 确保手机端宽公式和宽表格只在局部横向滚动。
4. 验证旧文章无封面、无新块时页面结构正常。

### 任务 9：全量检查与人工浏览器验收

**步骤**

1. 运行 Django 检查、迁移漂移检查和完整测试。
2. 本地创建非公开验收文章，覆盖全部新块。
3. 用桌面和手机视口检查 CMS 首页、列表、编辑、预览和前台。
4. 检查控制台错误、服务日志和无障碍基础行为。

**验证**

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check
.\.venv\Scripts\python.exe -m pytest -q
```

## 第四批：生产部署与回退验证

### 任务 10：备份、构建、部署和公开验收

**步骤**

1. 推送已测试提交，记录部署前镜像和提交号。
2. 备份生产数据库、媒体卷、环境文件和 Compose 配置，并独立验证备份校验值和可读取性。
3. 构建不可变镜像，先执行迁移计划与生产配置检查。
4. 部署后检查容器健康、迁移状态、CMS 登录/MFA、内容工作台、文章编辑/预览、主站、`www` 跳转和日志。
5. 检查 `hvac.sdzjoy.com` 及既有服务未受影响。
6. 若关键验收失败，恢复上一镜像；只有数据库迁移无法反向兼容时才按明确方案恢复数据库备份。

## 完成定义

- 旧文章和历史修订可继续打开、编辑、预览和发布；
- 新文章可使用全部专业块，公式错误不会造成 500 或源码丢失；
- 内容工作台、列表筛选和沉浸式编辑器按设计可用；
- 全量自动测试通过，人工桌面/手机验收通过；
- 生产部署有可验证备份、镜像回退点和部署记录；
- 主站、暖通参数站和其他保留服务均通过独立可用性检查。
