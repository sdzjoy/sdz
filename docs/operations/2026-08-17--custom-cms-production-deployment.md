# 自研 CMS 香港生产部署记录

记录日期：2026-08-17（Asia/Shanghai）

## 结论

- `sdzjoy.com` 已从 Wagtail 运行时切换到少惰主自研 CMS 最终镜像。
- 最终 Web 与 Worker 均运行 `sdzjoy-platform:task15-final-822731f`，健康且重启次数为 0。
- 生产数据库已到达 `publishing.0002`、`standards.0004`、`studio.0005`，迁移记录总数为 260。
- 最终运行镜像没有安装或加载 `Wagtail`、`modelcluster`、`taggit`。
- 主站、`www` 归一化、搜索、标准库、资源站、两条 RSS、站点地图、登录页、静态资源和 `hvac.sdzjoy.com` 均通过公网检查。
- CloudDrive2、两个 Cloudflare Tunnel、暖通参数库、Tailscale 与 ZeroTier 均保持运行。
- 用户明确选择以完整自动化验证替代受本地浏览器工具故障阻塞的桌面、手机人工视觉走查；这个例外不影响本次已完成的服务器端功能、数据和公网验证。

## 固定部署点

| 阶段 | Git 提交 | 镜像 | 镜像 ID |
| --- | --- | --- | --- |
| 切换前 | `f392b05a6aa8d2e92e4e7bc3c5b99f10ea2b94e0` | `sdzjoy-platform:f392b05` | 切换前容器记录已归档 |
| 兼容转换 | `7e86908deef2e8a5bd573ac89cdbc479f7dcf76d` | `sdzjoy-platform:task15-compat-7e86908` | `sha256:64c5ac72a44993f7954d6e3a9245b422f9766701390ff88ad86449bca5e281a8` |
| 最终运行 | `822731f3fe8db50f0e9b3ffae7b395f6857a5c4d` | `sdzjoy-platform:task15-final-822731f` | `sha256:843f1b78887fc8331bfd48c99ce950ef741ce062cbd6aaf29f07c205aeb04d18` |

服务器部署状态文件已更新为：

- 当前：最终镜像与 `822731f`；
- 上一版本：兼容镜像与 `7e86908`；
- 更早的 `f392b05` 状态文件已收入上线前备份。

生产 `.env` 中的默认 `APP_IMAGE` 也已固定为最终镜像，使用项目名
`sdzjoy-preview` 解析编排时得到的应用镜像与当前 Web、Worker 完全一致，避免日后普通
`docker compose up` 意外重建回旧版。原 `.env` 已包含在切换前的私有配置备份中，更新后
文件的 SHA-256 另行写入根权限部署证据，但没有把环境内容或密钥复制到报告。

## 上线前备份与恢复演练

根目录仅允许 `root` 访问：

```text
/opt/sdzjoy-deployment-backups/20260817T012101Z-cms-replacement
```

备份包含：

- 完整数据库与媒体备份包 `sdzjoy-20260817T012101Z.tar.gz`；
- 环境文件、生产与预览编排、Nginx 配置、Tunnel 私有配置和部署状态的加密边界内归档；
- 切换前源码归档、容器与数据卷清单、公开基线；
- 兼容阶段数据库检查点 `compat-stage.pgcustom`；
- 兼容导入的预演、执行、只读核对和最终迁移后核对报告；
- 两次状态切换前的部署状态、迁移输出、稳定性记录和本次异常处置记录；
- 对目录中所有证据文件生成的 `SHA256SUMS`。

权限与验证结果：

- 备份目录为 `0700`，敏感文件和报告为 `0600`，所有者为 `root:root`；
- 完整备份包自身 SHA-256 为 `07f904b83c5787c0fd525d1ae237dcc0a83c381cc7c7c348302ddd8df75f76b5`；
- 完整包内部数据库、媒体、清单和校验文件均通过校验；
- 数据库恢复到独立 PostgreSQL 17 容器、独立网络和独立数据卷后，用户、迁移、旧页面及各类新内容数量与生产基线完全一致；
- 恢复演练结束后，临时容器、网络和数据卷均已删除并验证不存在。

## 兼容迁移

兼容镜像先在生产数据库执行 `publishing` 与 `studio` 新表迁移，然后按以下顺序处理旧内容：

1. 默认预演，事务回滚；
2. 正式转换；
3. `--verify-only` 只读核对；
4. 切换兼容 Web 与 Worker；
5. 验证账号、MFA、站长角色、公开页面和日志。

三份转换报告的差异均为 0、关键问题均为 0。生产基线没有文章、项目、随记、工具、主题或图片，转换只补齐 1 条站点资料；原 7 条 Wagtail 页面和旧迁移历史均继续保留在数据库中作为回退证据。

兼容镜像上线后，Web 与 Worker 健康、重启次数为 0；当前账号保持启用、员工和超级用户状态，前台等级为 L3，已有 MFA 验证器不少于 2 个，后台解析为站长角色。

## 最终迁移与功能验证

最终镜像执行 `standards.0004_repoint_content_relations` 后：

- 旧关联表仍保留 `articlepage_id` 与 `toolpage_id`；
- 新关联表独立使用 `article_id` 与 `tool_id`；
- 兼容镜像在最终数据库上再次执行 Django 检查通过；
- 兼容核对命令再次得到差异 0、关键问题 0。

最终容器中的运行时检查确认：

- `Wagtail`、`modelcluster`、`taggit` 均不可导入；
- 三者均不在 `INSTALLED_APPS`；
- `studio-owner`、`studio-editor`、`studio-resource-admin` 三个后台组均存在；
- 当前超级用户仍解析为站长，L3 和 MFA 状态保持不变。

真实写作链路在生产数据库事务中完成并整体回滚：

1. 已登录站长打开后台首页、内容列表、新建文章和素材库，四页均为 200；
2. 新建临时草稿；
3. 发布并生成不可变公开快照；
4. 公开文章详情可读取；
5. 搜索文档、发布版本和后台审计记录均已产生；
6. 回滚整个事务；
7. 再次确认内容、版本、搜索和审计数量全部恢复到测试前的 0。

因此验证覆盖了真实生产配置和真实生产数据库，但没有向正式站留下测试内容。

## 公网与旁路服务

以下地址均通过 HTTPS 公网检查：

- `https://sdzjoy.com/`：200；
- `https://www.sdzjoy.com/`：308 归一化到主域，跟随跳转后 200；
- 搜索、标准库、资源站：200；
- `feeds/articles.xml`、`feeds/notes.xml`、`sitemap.xml`：200；
- 登录页、主站与后台样式文件：200；
- `/cms/` 未登录时正确跳转登录页；
- `https://hvac.sdzjoy.com/`：200。

旁路状态：

- CloudDrive2：容器继续运行；
- 主站与暖通参数库 Cloudflare Tunnel：容器继续运行；
- 暖通参数库 Web：健康；
- Tailscale：服务 active、后端 Running、本机 Online；
- ZeroTier：服务 active、节点 ONLINE，版本 1.16.2。

## 部署中发现并处置的问题

### 1. 隔离空项目

第一次最终迁移命令未固定 Compose 项目名，创建了名为 `sdzjoy-production` 的独立空数据库、空数据卷和独立网络。生产基线清单证明这些资源在部署前不存在，现有 `sdzjoy-preview` 数据库与应用容器均未被该命令寻址。

处置：

1. 在切换前发现生产迁移记录仍为 259，确认真实生产库没有执行最终迁移；
2. 保存空项目的迁移和检查输出；
3. 删除刚创建的空容器、空数据卷与独立网络，并验证不存在；
4. 后续所有命令固定使用 `-p sdzjoy-preview`；
5. 在真实生产库成功应用 `standards.0004`，迁移记录变为 260。

### 2. Nginx 缓存旧 Web 容器地址

最终 Web 容器重建后，Nginx 仍短暂使用旧容器地址，健康页曾返回 502。Web 与 Worker 本身当时均已健康。

处置：

1. `nginx -t` 通过后重新加载代理；
2. 下一次探测中 `/healthz/` 与 `/readyz/` 均恢复 200；
3. Worker 首轮监控产生的 4 条临时错误在下一轮检查中全部恢复；
4. 当前待处理告警为 0，最近 5 项关键路径检查全部正常。

后续重建 Web 容器时必须同步重新加载代理，或改造为动态解析容器 DNS，避免再次出现这个短窗口。

## 稳定性观察

- 最终 Web 与 Worker 从 2026-08-17 09:35（Asia/Shanghai）起持续运行；
- 连续 4 次、每 15 秒一次的检查全部得到：Web 健康、Worker 健康、重启 0、主站 200、就绪页 200、暖通参数库 200；
- 从代理恢复点之后筛查 Web 与 Worker 日志，关键 5xx、Traceback、未处理异常和 `http_error` 均为 0；
- 定时任务连续失败数为 0，`last_error` 为空；
- 当前无需回退。

## 回退方法

仅当最终应用出现问题、数据库仍可兼容读取时，回退到兼容镜像：

```sh
cd /opt/sdzjoy-preview
sudo sed -i \
  's|^APP_IMAGE=.*$|APP_IMAGE=sdzjoy-platform:task15-compat-7e86908|' \
  .env
sudo env APP_IMAGE=sdzjoy-platform:task15-compat-7e86908 \
  docker compose -p sdzjoy-preview -f compose.production.yml \
  up -d --no-deps --force-recreate web worker
sudo docker exec sdzjoy-preview-proxy-1 nginx -t
sudo docker exec sdzjoy-preview-proxy-1 nginx -s reload
curl --fail --silent --show-error http://127.0.0.1:18080/readyz/
```

新旧标准关联表并存，因此这一步不要求倒退数据库迁移。回退后还应检查公开首页、登录、搜索、标准库、Worker 健康和日志。

如果出现不兼容写入、数据数量差异或数据库损坏：

1. 停止本项目 Web 与 Worker，避免继续写入；
2. 保留现场数据库快照和日志；
3. 核对上述备份目录中的 `SHA256SUMS`；
4. 使用已经演练过的完整备份恢复数据库与媒体；
5. 恢复兼容镜像，再逐项验证数据数量、账号/MFA、后台角色和公网路径。

数据库恢复属于破坏性操作，不做无人值守自动执行，也不得影响暖通参数库、CloudDrive2、Tailscale、ZeroTier 或其他容器。
