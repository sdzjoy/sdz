# 少惰主（SDZJOY）技术工作台

这是 `sdzjoy.com` 站群的代码仓库。产品和架构决策见：

- [已批准设计](docs/plans/2026-08-15--sdzjoy-technology-workbench-design.md)
- [分批实施计划](docs/plans/2026-08-15--sdzjoy-implementation-plan.md)

## 本地开发

需要 Python 3.12。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements\dev.txt
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py runserver
```

默认开发设置使用 `var/db.sqlite3`，便于快速启动。需要用 Docker Compose 时，再把 `.env.example` 复制为 `.env` 并替换其中的示例密钥和密码；Compose 使用 PostgreSQL，与预览和生产环境保持一致。

## 验证

```powershell
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python manage.py makemigrations --check --dry-run
.\.venv\Scripts\python manage.py check
```

## 安全边界

- 不要提交 `.env`、密码、令牌、网盘凭据或生产数据。
- 生产和预览环境必须使用 PostgreSQL。
- 现有 `hvac.sdzjoy.com` 在新站群验收前保持独立运行。

## 生产运行与恢复

生产编排文件是 `compose.production.yml`，仅把反向代理绑定到本机
`127.0.0.1:8080`，PostgreSQL 没有宿主机端口。Cloudflare Tunnel 只需指向这个
本机入口；暖通参数库保持独立，不在本编排文件中。

上线前复制 `.env.production.example` 为服务器上的 `.env`，逐项换成独立密钥。
生产发布必须使用不可变镜像摘要，并通过 `ops/deploy.sh` 执行；脚本会先生成数据库
与媒体快照，迁移或健康检查失败时恢复上一镜像。`ops/rollback.sh` 只回退本项目的网页
和后台任务，不操作数据库，也不触碰暖通服务。

每日备份可由宿主机定时执行：

```sh
docker compose -f compose.production.yml --profile backup run --rm backup
```

`ops/systemd/` 提供每日 03:40（上海时区）的 service/timer 示例；实际安装前应按服务器
目录修改其中的 `/opt/sdzjoy`，再启用 timer。服务会保留日志轮转，且异地副本同时上传
独立 SHA-256 文件。

配置异地目标后，备份脚本强制要求 age 公钥并只上传加密副本。恢复演练始终使用隔离的
`restore-db` 和独立数据卷：

```sh
docker compose -f compose.production.yml --profile restore-drill up -d restore-db
docker compose -f compose.production.yml --profile restore-drill run --rm restore
```

每次演练会验证文件校验和、恢复迁移记录与抽样用户数据，并把结果写入备份卷的
`drills/` 目录。任何生产数据库恢复都不由自动回滚脚本执行，需在维护窗口内人工确认。

## 受保护预览环境

预览环境在独立 Compose 项目中运行，并额外加载 `compose.preview.yml`。它使用独立的
PostgreSQL、媒体卷、网络和本机回环端口；Cloudflare Tunnel 令牌只保存在服务器的
`private/tunnel-token`，不得提交到 Git。

```sh
docker compose -f compose.production.yml -f compose.preview.yml config
docker compose -f compose.production.yml -f compose.preview.yml up -d
```

服务器 `.env` 应将 `DJANGO_ALLOWED_HOSTS`、`DJANGO_CSRF_TRUSTED_ORIGINS`、
`PUBLIC_SITE_ORIGIN`、`TURNSTILE_EXPECTED_HOSTNAMES` 和 `SDZJOY_PORT` 设置为预览环境的
独立值。预览域名必须先通过 Cloudflare Access 保护，再创建公开 DNS 路由。
