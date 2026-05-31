# 线上记账工具

当前版本已从 V1 骨架升级为可生产部署版本（FastAPI + MySQL + Vue3 + Docker），核心能力覆盖：

- JWT 登录与角色权限（super_admin/admin/bookkeeper/platform_viewer）
- 主数据管理（平台、班次、项目、支付方式、账户）
- 批量流水录入（支持同日/同平台/同班次多笔）
- 三方对冲快捷录入（充值与兑奖一键双分录）
- 日汇总自动重算
- 月汇总按日汇总聚合
- 账户快照与差额计算
- Excel 多 Sheet 导出
- 审计日志 + 操作日志
- 多租户权限隔离（超管全域、租户按绑定范围）
- 超管后台：租户管理、平台报表、平台余额、后台用户、平台日志、平台工具
- 系统备份恢复（全库/租户）、手动服务器备份、备份文件管理
- 恢复结果可视化反馈（写入条数、自动修复外键条数）

## 近期关键变更（2026-05）

- 超管路由与菜单按模块权限严格拦截，修复 `/super` 回跳和循环问题
- 新增超管模块权限键 `super.users`（后台用户）
- 租户用户管理强化：`admin` 账号不可被同级删除/改权（仅支持重置密码）
- 系统工具页精简：超管只保留备份恢复核心能力
- 恢复接口新增结果字段：`restored_counts`、`total_rows`、`restored_file`
- 恢复时自动修复历史脏数据中的用户外键引用（如 `transactions.operator_id`）
- 前端恢复失败统一报错（含 HTTP 状态），避免“无反应”
- Nginx 增加大文件上传限制：`client_max_body_size 200m`

## 本地启动（先测）

### 1) 启动后端

1. 准备 MySQL 数据库，创建数据库 `accounting`
2. 进入目录：`backend`
3. 创建虚拟环境并安装依赖（Windows PowerShell）

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

4. 复制 `.env.example` 为 `.env` 并填写数据库连接
5. 运行：

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

6. 首次初始化管理员：`POST /auth/seed-admin`
7. 登录账号：`admin / admin123456`

### 2) 启动前端

```bash
cd frontend
npm install
npm run dev
```

浏览器访问：`http://127.0.0.1:5173`

### 3) 构建前端发布包

```bash
cd frontend
npm run build
```

构建产物目录：`frontend/dist`

## 已提供接口（核心）

- `GET /health`
- `POST /auth/seed-admin`
- `POST /auth/login`
- `POST /master/platforms`
- `POST /master/shifts`
- `POST /master/categories`
- `POST /master/payment-methods`
- `POST /master/accounts`
- `POST /transactions/batch`
- `POST /transactions/offset`
- `GET /reports/daily`
- `GET /reports/monthly?year=2026&month=5`
- `POST /balances/rebuild?bill_date=2026-05-29&shift_id=1`
- `GET /balances/daily?bill_date=2026-05-29&shift_id=1`
- `PATCH /balances/{snapshot_id}/actual`
- `GET /exports/excel?year=2026&month=5`
- `GET /transactions?page=1&page_size=20`
- `PUT /transactions/{id}`
- `DELETE /transactions/{id}`
- `POST /reports/monthly/rebuild?year=2026&month=5`
- `GET /reports/dashboard`
- `GET /system/logs?page=1&page_size=20`
- `GET /system/charts/income-expense-trend`
- `GET /system/charts/profit-by-platform`

## 仍需补强（建议）

- 增加更细粒度权限菜单与字段级鉴权
- 增加前端编辑弹窗、批量导入、移动端快捷数字键盘优化
- 增加自动备份任务和月账锁定正式流程

## 数据安全增强（已加入）

### 1) 月账锁定（防止历史月份被误改）

- 查询锁定列表：`GET /system/month-locks`
- 锁定某月（管理员）：`POST /system/month-lock?year=2026&month=5`
- 解锁某月（管理员）：`DELETE /system/month-lock?year=2026&month=5`

锁定后，以下操作会返回 `423`：

- `POST /transactions/batch`
- `POST /transactions/offset`
- `PUT /transactions/{id}`
- `DELETE /transactions/{id}`
- `POST /reports/monthly/rebuild`

### 2) 自动备份脚本（可配计划任务）

```bash
cd backend
python scripts/backup_runner.py --output ./backups --keep 30
```

- `--output`：备份目录
- `--keep`：最多保留文件数（超出会自动删旧文件）

### 3) Alembic 迁移脚手架（正式迁移起点）

已加入 `backend/alembic.ini` 与 `backend/alembic/`。

建议首上生产执行：

```bash
cd backend
alembic -c alembic.ini stamp 20260529_0001
```

后续新增字段/表请统一走 Alembic revision + upgrade。

## Docker 正式部署

### 1) 准备生产环境变量

在项目根目录复制一份：

```bash
cp .env.prod.example .env.prod
```

并修改 `.env.prod` 中的密钥和数据库密码。

### 2) 构建并启动

```bash
docker compose --env-file .env.prod up -d --build
```

访问：`http://服务器IP/`

### 3) 后续更新（代码构建）

```bash
git pull --ff-only origin main
docker compose --env-file .env.prod up -d --build
docker compose --env-file .env.prod exec -T backend sh -lc 'cd /app && alembic -c alembic.ini upgrade head'
```

如果提示 `No config file 'alembic.ini' found`，通常是旧镜像未包含 Alembic 文件；拉取最新代码并 `--build` 重建后再执行上面的命令。

### 4) 后续更新（仅拉镜像）

```bash
docker compose --env-file .env.prod pull
docker compose --env-file .env.prod up -d
```

### 5) GitHub Actions 自动发布镜像

仓库已提供工作流：`.github/workflows/docker-publish.yml`

请在 GitHub 仓库 `Settings -> Secrets and variables -> Actions` 新增：

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

推送到 `main` 后会自动构建并推送：

- `tt523-cpu/ledger-system-backend:latest`
- `tt523-cpu/ledger-system-frontend:latest`

## 部署脚本注意事项（重要）

- 你的一键部署脚本里“重置管理员账号”逻辑可用，模型字段应使用 `password_hash`（不是 `hashed_password`）。
- 如果刚执行过“恢复备份(JSON)”，登录密码以备份中的用户数据为准，可能覆盖掉部署脚本刚重置的密码。
- 建议将“重置管理员密码”放在恢复之后，或作为独立运维命令手动执行。

推荐密码重置命令：

```bash
docker compose --env-file .env.prod exec -T backend python - <<'PY'
from sqlalchemy import select
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.entities import User
from app.models.enums import GenericStatus, UserRole

db = SessionLocal()
try:
    user = db.execute(select(User).where(User.username == "admin")).scalar_one_or_none()
    if user is None:
        user = User(
            username="admin",
            password_hash=get_password_hash("admin123456"),
            role=UserRole.SUPER_ADMIN.value,
            status=GenericStatus.ENABLED.value,
        )
        db.add(user)
    else:
        user.password_hash = get_password_hash("admin123456")
        user.role = UserRole.SUPER_ADMIN.value
        user.status = GenericStatus.ENABLED.value
    db.commit()
    print("管理员账号已设置：admin / admin123456")
finally:
    db.close()
PY
```
