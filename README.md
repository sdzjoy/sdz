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
