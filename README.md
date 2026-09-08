# AutoInsight Car2026 后端

基于 FastAPI + MySQL + SQLAlchemy 的汽车行业数据分析后端服务，与 [car2026 前端](https://github.com/gfy200627-dot/car2026) 全契约对接。

## 技术栈

- **框架**: FastAPI（异步、自动 OpenAPI 文档）
- **数据库**: MySQL 8（utf8mb4），ORM SQLAlchemy 2+，迁移 Alembic；本地演示可用 SQLite
- **认证**: JWT（python-jose）+ bcrypt 密码哈希
- **算法**: 销量预测（趋势 + 季节因子外推，结果落库）、购车推荐（多维加权打分）、舆情（评价情感标注聚合）
- **契约**: 路由与响应结构完全对齐前端 `src/mock/handlers.ts`（49 条 API），字段驼峰输出

## 项目结构

```
car2026-backend/
├─ app/
│  ├─ main.py                 # FastAPI 主入口（CORS / 异常处理器 / 路由注册）
│  ├─ core/                   # config（环境变量）/ security（JWT+bcrypt）/ envelope（统一错误外壳）
│  ├─ models/                 # SQLAlchemy Models（18 张表，__init__ 统一导出）
│  ├─ schemas/                # Pydantic Schemas（对齐 src/types/*，契约文档）
│  ├─ api/                    # auth/dashboard/cars/market/sales/recommendations/predictions/sentiment/admin
│  ├─ database/session.py     # engine / SessionLocal / get_db
│  └─ utils/                  # series（月份序列）/ serialize（车型序列化与分页）/ rng（确定性随机）
├─ scripts/
│  ├─ seed_demo.py            # 全量演示数据生成（与前端 Mock 同口径）
│  └─ smoke_test.py           # 启动服务后的端到端冒烟测试
├─ alembic/                   # 数据库迁移（可选，seed_demo 亦可直接建表）
├─ tests/test_api.py          # 契约测试（sqlite 内存库 + TestClient）
├─ requirements.txt
└─ .env.example
```

## 快速开始

### 1. 安装依赖

```bash
# 方式一：uv（推荐）
uv venv .venv
uv pip install -r requirements.txt -p .venv

# 方式二：pip
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，修改 DATABASE_URL 与 SECRET_KEY
```

本地无 MySQL 时可直接用 SQLite（在 `.env` 中设置）：

```
DATABASE_URL=sqlite:///./car2026.db
```

### 3. 初始化数据库与种子数据

```bash
python scripts/seed_demo.py
```

脚本自动建表并导入与前端 Mock 同口径的演示数据：30 品牌 / 34 地区 / 158 车型 / 24 个月销量
（含品牌、能源、地区聚合）/ 46 用户 / 库存 60 / 订单 160 / 算法任务 6 / 日志 120 / 评价 240（含情感标注）/ 预测快照 948。
重复执行自动跳过已导入部分；`--fresh` 清空业务数据后重新生成。

MySQL 生产环境可改用 Alembic 管理结构：

```bash
alembic upgrade head
```

### 4. 启动服务

```bash
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

访问 http://localhost:8000/docs 查看 API 文档。

### 5. 前端对接

在 `car2026` 前端项目中：

```bash
# .env.development
VITE_USE_MOCK=false
VITE_API_BASE_URL=/api
```

Vite 代理已配置 `^/api` → `http://127.0.0.1:8000`。

## 演示账号

| 用户名 | 密码 | 角色 | 说明 |
|---|---|---|---|
| admin | admin123 | admin | 系统管理员（全部权限） |
| analyst | analyst123 | analyst | 数据分析师（分析与预测） |
| sales | sales123 | sales | 销售运营（车型/订单/库存） |
| user | user123 | user | 普通用户（浏览与推荐） |

## 核心设计

### 数据库 ER 图

```
brands ──1:N──> cars ──1:N──> car_sales（UNIQUE car_id+month）
   │              │              │
   │              │              └──(聚合)──> brand_sales / energy_sales / regional_sales
   │              ├──1:N──> reviews ──1:1──> sentiments
   │              ├──1:N──> sales_predictions（UNIQUE car_id+month+model）
   │              ├──1:N──> inventory
   │              └──1:N──> orders
   └──1:N──> brand_sales
users ──1:N──> operation_logs        collection_logs（独立采集日志）
```

### API 契约对齐

- 路由与前端 `src/api/*.ts` 完全一致（认证/驾驶舱/车型/市场/销量/推荐/预测/舆情/后台）
- 成功响应直出业务数据；错误返回 HTTP 状态码 + `{ code, message }` 外壳
  （前端 `src/utils/request.ts` 对「裸数据」与「envelope」均兼容）
- 未认证：HTTP 401（前端自动登出）；越权：HTTP 403
- 字段驼峰输出，命名对齐 `src/types/business.ts`（如 Car 的 `range/battery/power/torque/sales`）
- 能源口径：数据库层 `EREV` 在 API 输出层并入 `PHEV`（乘联会口径）

### 算法说明

- **销量预测** `GET /api/predict/sales`：近 6 月线性趋势 + 季节因子 + 确定性扰动外推，
  置信区间随步长放大；每次调用结果幂等落库 `sales_predictions`
- **购车推荐** `POST /api/recommend`：硬约束过滤（预算/能源）→ 价格/续航/场景/四项评分多维打分
  → 按用户关注因素加权排序，快照写入 `recommendations`（request_hash 幂等）
- **舆情情感**：`reviews` 表逐条带 `sentiments` 标注（label/score/keywords），聚合产出概览/趋势/关键词/品牌口碑

## 测试

```bash
# 契约测试（sqlite 内存库自动种子，无需外部服务）
pytest tests/ -v

# 端到端冒烟（先启动服务并完成种子导入）
set DATABASE_URL=sqlite:///./car2026.db
python scripts/seed_demo.py
python -m uvicorn app.main:app --port 8000
python scripts/smoke_test.py
```

契约测试覆盖全部 9 个 API 模块的响应结构，字段断言对齐前端 `src/types/*`。

## 部署

- 环境：生产环境 `APP_ENV=production`，务必更换 `SECRET_KEY`
- 数据库：MySQL 使用连接池配置（`pool_pre_ping` 已开启）
- 运行：`uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4`

## 许可

MIT

---

**仓库**: https://github.com/gfy200627-dot/car2026-backend
**前端**: https://github.com/gfy200627-dot/car2026
