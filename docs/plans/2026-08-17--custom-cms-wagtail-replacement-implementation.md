# 少惰主自有 CMS 替换 Wagtail 实施计划

- 设计依据：`docs/plans/2026-08-17--custom-cms-wagtail-replacement-design.md`
- 实施分支：`feat/custom-cms-replacement`
- 公开切换：一次；内部交付：兼容迁移镜像与无 Wagtail 最终镜像两个检查点
- 核心原则：先备份与校验，再切换；不伪造迁移状态；不改公开视觉与 URL；每批独立测试和提交

## 目标架构

- `publishing`：普通 Django 内容模型、正文协议、服务端渲染、公开查询与迁移工具；
- `studio`：`/cms/` 后台、权限、写作界面、自动保存、版本、素材；
- `frontend`：Tiptap + TypeScript + Vite 的自托管编辑器静态资源；
- `accounts`、`standards`、`resources`、`notifications`、`searchapp`：保留并改接新模型；
- `content` 与 Wagtail 页面模型：只在兼容迁移镜像中读取，最终镜像不安装、不导入；
- `core` 中与 Wagtail 无关的站点壳、健康检查和规范化域名逻辑迁入普通 Django 代码后退出旧页面模型。

## 第一批：新系统基础，不触碰现有公开运行路径

### 任务 1：建立 Tiptap 前端构建与测试底座

**文件**

- 新增：`frontend/package.json`
- 新增：`frontend/pnpm-lock.yaml`
- 新增：`frontend/tsconfig.json`
- 新增：`frontend/vite.config.ts`
- 新增：`frontend/src/editor.ts`
- 新增：`frontend/src/editor.css`
- 新增：`frontend/src/editor.test.ts`
- 修改：`.gitignore`
- 修改：`Dockerfile`

**步骤**

1. 锁定同一版本的 `@tiptap/core`、`@tiptap/pm`、`@tiptap/starter-kit` 与表格扩展。
2. 使用 TypeScript 和 Vite 输出到 `static/studio/dist/`，生产环境不运行 Node 服务。
3. 建立无框架 Tiptap 初始化函数，支持标题、段落、强调、列表、引用、链接、撤销重做与表格。
4. 为 JSON 初始值、内容更新回调、只读切换和销毁行为写前端单元测试。
5. 把 Dockerfile 改成前端构建 + Python 运行的多阶段镜像，并只复制构建产物。

**验证**

```powershell
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend test
pnpm --dir frontend build
```

### 任务 2：实现版本化正文协议、验证与安全渲染

**文件**

- 新增：`publishing/__init__.py`
- 新增：`publishing/apps.py`
- 新增：`publishing/documents/__init__.py`
- 新增：`publishing/documents/schema.py`
- 新增：`publishing/documents/render.py`
- 新增：`publishing/documents/text.py`
- 新增：`tests/test_publishing_documents.py`
- 修改：`config/settings/base.py`

**步骤**

1. 定义 `schema_version=1` 文档包络与允许的 Tiptap 节点、标记、属性和协议。
2. 限制 JSON 总体积、树深度、节点数、文本长度、链接协议和属性范围。
3. 服务端从 JSON 生成 HTML；所有文本和属性先转义，再用 `nh3` 做最终白名单净化。
4. 未知节点保留原 JSON，并在 HTML 中降级为安全占位内容，不使整篇文章报错。
5. 从同一 JSON 抽取 `body_text`，供搜索、摘要和阅读时间使用。
6. 覆盖正常正文、嵌套列表、表格、危险链接、脚本属性、畸形结构、超限输入和未知节点测试。

**验证**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_publishing_documents.py -q
.\.venv\Scripts\python.exe -m ruff check publishing tests\test_publishing_documents.py
```

### 任务 3：建立普通 Django 内容模型和兼容迁移

**文件**

- 新增：`publishing/models.py`
- 新增：`publishing/managers.py`
- 新增：`publishing/admin.py`
- 新增：`publishing/migrations/0001_initial.py`
- 新增：`publishing/services/content.py`
- 新增：`publishing/services/revisions.py`
- 新增：`tests/test_publishing_models.py`

**步骤**

1. 建立 `Topic`、`Asset`、`SiteProfile`、`Article`、`Project`、`Note`、`Tool` 与 `ContentRevision`。
2. 发布类内容共享草稿、线上快照、作者、别名、主题、封面、推荐、乐观锁、软删除与发布时间语义。
3. 草稿正文使用 `body_json/rendered_html/body_text`；线上版本使用独立快照字段，编辑草稿不改变公开内容。
4. 手工保存、发布和恢复前创建版本；自动保存不创建版本；每项内容保留最近 30 个版本。
5. 数据库约束覆盖类型、状态、非负锁版本、别名唯一性和版本动作。
6. 测试保存、发布、取消发布、恢复、回收站、阅读时间、别名冲突和多窗口版本冲突。

**验证**

```powershell
.\.venv\Scripts\python.exe manage.py makemigrations --check
.\.venv\Scripts\python.exe manage.py migrate --plan
.\.venv\Scripts\python.exe -m pytest tests\test_publishing_models.py tests\test_publishing_documents.py -q
```

## 第二批：简单后台骨架与文章主流程

### 任务 4：后台访问控制、壳和首页

**文件**

- 新增：`studio/__init__.py`
- 新增：`studio/apps.py`
- 新增：`studio/urls.py`
- 新增：`studio/permissions.py`
- 新增：`studio/views/dashboard.py`
- 新增：`studio/templates/studio/base.html`
- 新增：`studio/templates/studio/dashboard.html`
- 新增：`static/studio/studio.css`
- 修改：`config/settings/base.py`
- 修改：`config/urls.py`
- 修改：`accounts/middleware.py`
- 新增：`tests/test_studio_access.py`

**步骤**

1. 建立站长、编辑、资料管理员三个后台角色，和前台会员等级完全分离。
2. `/cms/` 要求登录、后台角色和已配置 MFA；未授权请求返回明确的登录或权限页面。
3. 实现“首页、内容、资料库、用户、设置”五项中文导航和“写文章”主操作。
4. 后台响应统一 `private, no-store`，所有写接口启用 CSRF 与审计上下文。
5. 首页显示最近草稿、最近发布、待处理事项和简洁统计。

### 任务 5：内容列表、筛选与回收站

**文件**

- 新增：`studio/views/content.py`
- 新增：`studio/forms/content.py`
- 新增：`studio/templates/studio/content/list.html`
- 新增：`studio/templates/studio/content/_rows.html`
- 新增：`tests/test_studio_content_list.py`

**步骤**

1. 默认列出文章，可切换项目、随记、工具和独立页面。
2. 实现标题搜索及状态、主题、日期筛选；高级筛选默认收起。
3. 批量操作只保留发布、取消发布和移入回收站。
4. 普通删除只软删除；永久删除仅站长可用并记录原因。
5. 检查列表查询数量，避免逐行追加数据库请求。

### 任务 6：文章所见即所得编辑页与可靠自动保存

**文件**

- 新增：`studio/views/editor.py`
- 新增：`studio/api/articles.py`
- 新增：`studio/templates/studio/editor/article.html`
- 新增：`frontend/src/article-editor.ts`
- 新增：`frontend/src/autosave.ts`
- 新增：`frontend/src/autosave.test.ts`
- 新增：`tests/test_studio_article_editor.py`

**步骤**

1. 实现全宽编辑页、固定顶部栏、标题、摘要、正文和默认收起的文章设置抽屉。
2. 输入停止后延迟自动保存，并增加低频保底保存；自动保存只更新草稿，不产生版本。
3. 页面显示保存中、已保存、离线、失败和冲突状态；支持 `Ctrl+S` 手工保存。
4. 本地缓存未同步 JSON；重连时携带服务器锁版本，冲突则生成副本而不覆盖。
5. 发布使用事务：先保存版本，再写线上快照；失败时线上内容保持不变。

## 第三批：素材、专业内容与版本管理

### 任务 7：素材库与安全图片上传

**文件**

- 新增：`publishing/uploads.py`
- 新增：`studio/api/assets.py`
- 新增：`studio/views/assets.py`
- 新增：`studio/templates/studio/assets/list.html`
- 新增：`frontend/src/extensions/image.ts`
- 新增：`tests/test_asset_uploads.py`

**步骤**

1. 验证文件头、真实 MIME、大小、尺寸和像素总量，重新生成安全文件名。
2. 支持选择、拖拽和剪贴板上传；上传完成后才插入编辑器。
3. 素材库支持搜索、复制地址和查看引用位置。
4. 删除仍被引用的素材时阻止操作并列出引用内容。

### 任务 8：工具栏、斜杠菜单与粘贴清理

**文件**

- 新增：`frontend/src/toolbar.ts`
- 新增：`frontend/src/slash-menu.ts`
- 新增：`frontend/src/paste.ts`
- 新增：`frontend/src/paste.test.ts`
- 修改：`frontend/src/article-editor.ts`

**步骤**

1. 实现一行常驻工具栏、选区浮动工具栏和可搜索 `/` 菜单。
2. 清理 Word、网页和微信公众号粘贴内容，保留语义结构，删除来源样式与危险节点。
3. 外部图片不静默保存临时地址；提示重新上传。
4. 清理失败时安全退回纯文本，中文输入法组合过程不触发错误保存。

### 任务 9：暖通专业节点与服务器渲染

**文件**

- 新增：`frontend/src/extensions/callout.ts`
- 新增：`frontend/src/extensions/equation.ts`
- 新增：`frontend/src/extensions/reference.ts`
- 新增：`frontend/src/extensions/parameter-card.ts`
- 新增：`frontend/src/extensions/cloud-resource.ts`
- 修改：`publishing/documents/schema.py`
- 修改：`publishing/documents/render.py`
- 修改：`publishing/documents/text.py`
- 新增：`tests/test_professional_nodes.py`

**步骤**

1. 实现提示框、公式、规范引用、参数卡、代码、分隔线和网盘资源自定义节点。
2. 公式保存原始 LaTeX，由服务器生成安全 MathML；失败时保留源码并安全降级。
3. 规范与资源节点只保存对象标识；服务端按当前数据与会员等级解析。
4. 未授权公开页面绝不包含受限链接或提取信息。

### 任务 10：版本历史、恢复和回收站清理

**文件**

- 新增：`studio/views/revisions.py`
- 新增：`studio/templates/studio/revisions/list.html`
- 新增：`studio/templates/studio/revisions/preview.html`
- 新增：`publishing/management/commands/purge_deleted_content.py`
- 新增：`tests/test_studio_revisions.py`

**步骤**

1. 版本页只显示时间、操作者、动作和修改摘要，并支持预览。
2. 恢复前先保存当前状态，使恢复本身可撤回。
3. 回收站 30 天后才允许站长彻底清理。
4. 对保存、发布、恢复、删除和永久清理记录审计信息。

## 第四批：公开站兼容与旧数据转换

### 任务 11：公开视图、模板、RSS 与站点地图改接

**文件**

- 新增：`publishing/urls.py`
- 新增：`publishing/views.py`
- 新增：`publishing/feeds.py`
- 新增：`publishing/sitemaps.py`
- 修改：公开站模板和上下文处理器
- 修改：`config/urls.py`
- 新增：`tests/test_public_publishing.py`

**步骤**

1. 保持首页、文章、项目、随记、工具和关于页面的现有 URL 与模板外观。
2. 公开查询只读取线上快照，草稿修改不改变访客页面。
3. RSS、站点地图、规范化 URL、面包屑和元数据改接新模型。
4. 为关键旧 URL 建立逐项状态码、标题、canonical 与内容回归清单。

### 任务 12：搜索、通知、规范引用与资源网盘权限改接

**文件**

- 修改：`searchapp/services.py`
- 修改：`searchapp/signals.py`
- 修改：`notifications/references.py`
- 修改：`resources` 中的内容引用接口
- 修改：相关测试

**步骤**

1. 搜索索引改用新模型 `body_text` 和线上状态。
2. 发布、取消发布和删除信号正确更新索引与通知。
3. 规范引用和资源网盘链接继续执行服务器端会员等级判断。
4. 验证既有账号、MFA、会员、通知、标准库与资源站行为不变。

### 任务 13：旧 Wagtail 数据转换、比对与幂等验证

**文件**

- 新增：`publishing/legacy/converter.py`
- 新增：`publishing/management/commands/import_wagtail_content.py`
- 新增：`publishing/management/commands/verify_legacy_content.py`
- 新增：`tests/fixtures/legacy_content.json`
- 新增：`tests/test_legacy_conversion.py`

**步骤**

1. 转换首页配置、主题、图片、文章、项目、随记、工具和关于内容。
2. 把旧 StreamField 块映射为版本化 Tiptap JSON；无法映射的块保留原数据并生成报告。
3. 命令支持预演、事务回滚、重复执行和只验证模式。
4. 按类型比较数量、标题、别名、公开 URL、发布状态、媒体引用与正文摘要哈希。
5. 任一关键差异使命令失败，阻止最终切换。

## 第五批：最终移除 Wagtail 与全量验收

### 任务 14：构建无 Wagtail 最终代码与全新数据库路径

**文件**

- 修改：`requirements/base.txt`
- 修改：`config/settings/base.py`
- 修改：`config/urls.py`
- 修改：`Dockerfile`
- 删除：旧 Wagtail 页面模型、钩子、模板和运行路由
- 新增：最终迁移历史验证脚本与测试

**步骤**

1. 移除 `Wagtail`、`modelcluster`、`taggit` 及所有 Wagtail 已安装应用、中间件、设置和导入。
2. `content/core` 旧页面应用退出最终 `INSTALLED_APPS`；旧迁移记录保留在生产数据库但不再由运行时加载。
3. 旧表仅在完整备份和转换核验通过后由明确的清理迁移处理。
4. 从空数据库执行全部最终迁移，证明无需 Wagtail 包或伪造迁移即可安装。
5. 全库搜索 `wagtail|modelcluster|taggit`，只允许历史设计/迁移说明中的文本命中。

### 任务 15：完整自动测试、浏览器与迁移演练

**步骤**

1. 运行 Django 检查、迁移漂移检查、前端测试/构建和完整 Python 测试。
2. 用生产备份副本依次演练兼容迁移、数据比对和最终镜像切换。
3. 桌面与手机验收后台首页、列表、编辑、图片、专业节点、自动保存、断网、冲突、预览、发布、版本和回收站。
4. 验收主站关键 URL、搜索、RSS、站点地图、账号/MFA、会员等级、标准库、资源站和通知。
5. 记录兼容镜像、最终镜像、数据库迁移点与可执行回退步骤。

## 第六批：香港生产部署与独立验证

### 任务 16：兼容迁移镜像部署

1. 记录当前提交、镜像、容器、数据库版本和公开端点基线。
2. 备份数据库、媒体、环境文件和编排配置；生成校验值并在隔离位置验证可读取和可恢复。
3. 部署仍含 Wagtail 读取能力的兼容镜像，执行新表迁移、旧内容导入和只读核验。
4. 关键差异、异常块或备份验证失败时停止，不进入最终切换。

### 任务 17：最终镜像切换与稳定性观察

1. 部署不含 Wagtail 的最终镜像并切换 `/cms/` 与公开内容查询。
2. 验证容器健康、迁移状态、MFA、三种后台角色、写作发布、公开 URL、搜索、RSS、站点地图和日志。
3. 从公网独立检查 `sdzjoy.com`、`www.sdzjoy.com`、`hvac.sdzjoy.com`，并确认 CloudDrive2、Tailscale 与 ZeroTier 未受影响。
4. 稳定观察窗口内若出现关键 5xx、数据差异或写入异常，按记录恢复旧镜像；若已发生不兼容写入，再恢复已验证数据库备份。

## 每批通用门禁

```powershell
pnpm --dir frontend test
pnpm --dir frontend build
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
```

每批提交前还要确认：工作树只有本批预期变更、迁移文件可解释、没有密钥或生产数据进入版本库、现有公开路径与无关服务测试未退化。

## 完成定义

- 最终依赖、设置、路由、模型、模板和镜像不再加载 Wagtail；
- 新数据库可从零安装，生产迁移不伪造历史且有恢复演练；
- 后台最多两次点击开始写作，Tiptap 所见即所得、自动保存、图片、专业节点、预览、发布、版本与回收站可用；
- 主站视觉、栏目、公开 URL、RSS、站点地图和搜索保持兼容；
- 账号、MFA、后台角色、会员等级、标准库、资源网盘链接与通知继续工作；
- 香港生产切换有可验证备份、明确回退点、独立公网验收和稳定性记录。
