# 线上记账工具 V1

当前已完成前后端第一版联调骨架（FastAPI + MySQL + Vue3），覆盖：

- JWT 登录与角色权限（管理员/记账员/查看）
- 主数据管理（平台、班次、项目、支付方式、账户）
- 批量流水录入（支持同日/同平台/同班次多笔）
- 三方对冲快捷录入（充值与兑奖一键双分录）
- 日汇总自动重算
- 月汇总按日汇总聚合
- 账户快照与差额计算
- Excel 多 Sheet 导出
- 审计日志基础记录
- 前端15个业务页面（登录、录入、查询、报表、图表、导出、基础管理）

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

- 增加 Alembic 正式迁移脚本（当前为 `create_all` 自动建表）
- 增加更细粒度权限菜单与字段级鉴权
- 增加前端编辑弹窗、批量导入、移动端快捷数字键盘优化
- 增加自动备份任务和月账锁定正式流程

## Docker 正式部署

### 1) 准备生产环境变量

在项目根目录复制一份：

```bash
cp .env.prod.example .env.prod
```

并修改 `.env.prod` 中的密钥和数据库密码。

### 2) 本机构建并启动

```bash
docker compose --env-file .env.prod up -d --build
```

访问：`http://服务器IP/`

### 3) 后续更新（拉镜像）

```bash
docker compose --env-file .env.prod pull
docker compose --env-file .env.prod up -d
```

### 4) GitHub Actions 自动发布镜像

仓库已提供工作流：`.github/workflows/docker-publish.yml`

请在 GitHub 仓库 `Settings -> Secrets and variables -> Actions` 新增：

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

推送到 `main` 后会自动构建并推送：

- `tt523-cpu/ledger-system-backend:latest`
- `tt523-cpu/ledger-system-frontend:latest`
