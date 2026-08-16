# 自研 CMS 任务 15 验收与迁移演练记录

记录时间：2026-08-17 05:39（Asia/Shanghai）

## 结论

- 自动化门禁、干净依赖安装、空库安装、容器构建、生产数据库副本恢复、兼容转换、最终迁移和应用回退兼容性均通过。
- 香港服务器上的现有预览栈保持 `sdzjoy-platform:f392b05`，未重启、未替换、未切换域名。
- `gb50736` 暖通参数库、CloudDrive2 和 Cloudflare Tunnel 均未修改。
- 应用内浏览器运行时因本地工具启动冲突无法连接，桌面和手机的人工视觉复核仍是生产切换前的未完成门禁。后端页面、接口和前端编辑器交互已由完整测试覆盖，但不能替代最后一次真实浏览器走查。

## 固定检查点

| 用途 | Git 提交 | 演练镜像 | 镜像 ID |
| --- | --- | --- | --- |
| 现有香港预览基线 | `f392b05` | `sdzjoy-platform:f392b05` | 由现有容器保留 |
| 兼容读取与旧内容转换 | `7e86908` | `sdzjoy-platform:task15-compat-7e86908` | `sha256:64c5ac72a44993f7954d6e3a9245b422f9766701390ff88ad86449bca5e281a8` |
| 无旧 CMS 最终运行时 | `822731f` | `sdzjoy-platform:task15-final-822731f` | `sha256:843f1b78887fc8331bfd48c99ce950ef741ce062cbd6aaf29f07c205aeb04d18` |

最终运行时另含 `7575db6` 的生产依赖修正：验证码请求代码使用的 `requests` 已成为显式生产依赖，不再依赖旧环境偶然带入。

## 自动化门禁

- 前端：8 个测试文件、21 项测试全部通过。
- TypeScript：`tsc --noEmit` 通过。
- Vite：生产构建通过。
- Python：158 项测试全部通过，总覆盖率 78.92%。
- Ruff：全库静态检查通过。
- Django：系统检查通过，迁移无漂移。
- 空数据库：最终迁移从零建立 72 张表，核心表检查通过。
- 干净 Python 3.12 环境：Django 5.2.17 和 requests 2.34.2 可用；`Wagtail`、`modelcluster`、`taggit` 均不存在；空库验证通过。
- 最终容器：构建阶段空库验证通过；运行镜像中三个退役包均不存在。

## 生产数据副本

来源为当前香港预览数据库，只读导出为 PostgreSQL custom-format 快照：

- 服务器路径：`/home/ubuntu/sdzjoy-task15-20260817-7575db6/preview.pgcustom`
- 大小：496392 字节
- SHA-256：`841ee210f693d547f41481752c73ab67ad22336072ba71ff28eaab2b77499478`
- 权限：目录仅属主可进入，快照与报告仅属主可读写。

源数据基线：

| 项目 | 数量 |
| --- | ---: |
| Wagtail 页面总数 | 7 |
| 文章 | 0 |
| 项目 | 0 |
| 随记 | 0 |
| 工具 | 0 |
| 主题 | 0 |
| 图片 | 0 |
| 用户 | 1 |

因此本次真实副本主要验证站点资料和迁移历史。富文本块、图片、主题、发布快照、收藏/订阅和标准关联的非空转换由迁移专用测试夹具覆盖。

## 演练顺序与结果

1. 把生产快照恢复到独立 PostgreSQL 17 容器、独立网络和独立数据卷。
2. 兼容镜像执行新表迁移，达到 `publishing.0002_legacy_source_ids`。
3. 默认预演完成且事务回滚；回滚后 `publishing_contententry` 仍为 0。
4. 正式转换完成；新增 0、更新站点资料 1、差异 0、关键问题 0。
5. `--verify-only` 独立复核完成；差异 0、关键问题 0。
6. 最终镜像执行 `standards.0004_repoint_content_relations` 并通过系统检查。
7. 最终数据库包含站点资料 1 条；内容条目 0 条，与源数据一致。
8. 最终镜像烟雾检查通过：首页、搜索、标准库、资源站、两条 RSS、站点地图和登录页均为 200；后台、账号、会员、通知和 MFA 页面在未登录状态正确重定向到登录页。
9. 最终迁移后再次运行兼容镜像，Django 系统检查通过。
10. 新旧标准关联表同时存在：旧表继续保留 `articlepage_id/toolpage_id`，新表独立使用 `article_id/tool_id`。应用镜像回退不会因关联表列被替换而失效。
11. 隔离容器、网络和数据卷均已删除；生产快照、JSON 报告和两个演练镜像保留。

JSON 报告位于服务器目录：

- `/home/ubuntu/sdzjoy-task15-20260817-7575db6/reports/dry-run.json`
- `/home/ubuntu/sdzjoy-task15-20260817-7575db6/reports/execute.json`
- `/home/ubuntu/sdzjoy-task15-20260817-7575db6/reports/verify.json`
- `/home/ubuntu/sdzjoy-task15-20260817-7575db6/reports/execute-rollback-safe.json`

## 生产切换前仍需完成

1. 恢复应用内浏览器连接后，在最终镜像上分别以桌面和手机视口走查：首页、内容列表、文章编辑器、图片库、专业节点、自动保存、断网副本、版本冲突、预览、发布、版本恢复和回收站。
2. 兼容镜像上线前，按任务 16 再生成包含数据库、媒体、环境文件和编排配置的完整加密备份；本记录中的数据库快照不能代替完整发布备份。
3. 在维护窗口禁止编辑写入，先部署兼容镜像并执行转换/核对，再部署最终镜像。

## 可执行回退步骤

以下命令只操作 SDZJOY 项目的应用容器，不操作暖通参数库、CloudDrive2、Tailscale 或 ZeroTier。

### 最终镜像健康失败，但没有发生最终系统写入

在服务器项目目录执行：

```sh
cd /opt/sdzjoy-preview
export APP_IMAGE="$(cat .deployment-state/previous-image)"
docker compose -f compose.production.yml -f compose.preview.yml up -d web worker proxy
curl --fail --silent --show-error http://127.0.0.1:8080/readyz/
```

迁移采用新旧关联表并存设计，因此兼容镜像可继续读取旧关联表。回退后保留最终新表，不做自动删表。

### 已发生最终系统写入、核对差异或数据库异常

1. 停止 `web` 和 `worker`，避免继续写入。
2. 保留故障现场快照。
3. 使用任务 16 上线前生成并完成恢复演练的完整备份恢复数据库和媒体。
4. 将应用镜像恢复到备份记录中的兼容镜像。
5. 依次验证数据库迁移点、`readyz`、公开页面、账号/MFA、后台角色和现有内容数量，再恢复入口流量。

数据库恢复属于破坏性操作，不放入自动回退脚本；必须在确认快照校验值和目标数据库后人工执行。

## 生产未变更证明

演练清理后的生产相关容器仍为：

- `sdzjoy-preview-web-1` 与 `sdzjoy-preview-worker-1`：`sdzjoy-platform:f392b05`，健康。
- `sdzjoy-preview-proxy-1`：健康。
- `sdzjoy-preview-db-1`：健康。
- `gb50736-web`：健康。
- `gb50736-tunnel`、`sdzjoy-preview-cloudflared-1`：继续运行。
- `clouddrive2`：继续运行。

公网基线保持：首页 `sdzjoy.com` 为 200，`www.sdzjoy.com` 正确归一到主域，`hvac.sdzjoy.com` 为 200。
