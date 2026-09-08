# AutoInsight Car2026 后端

基于 FastAPI + MySQL + SQLAlchemy + Alembic 的汽车行业数据分析后端服务，与 [car2026 前端](https://github.com/gfy200627-dot/car2026) 全契约对接。

## 技术栈

- **框架**: FastAPI 0.115+（异步、自动 OpenAPI 文档）
- **数据库**: MySQL 8（utf8mb4），ORM SQLAlchemy 2+，迁移 Alembic
- **认证**: JWT + bcrypt 密码哈希
- **数据源**: 公开渠道（乘联会、中汽协、工信部）+ 人工导入 CSV
- **算法**: scikit-learn（销量预测） + snownlp（情感分析）
- **契约**: 完全对齐前端 `src/mock/handlers.ts`（49 条 API），字段驼峰输出

## 项目结构

```
car2026-backend/
├─ app/
│  ├─ main.py                 # FastAPI 主入口
│  ├─ core/(config,envelope,security)    # 配置/统一响应/JWT
│  ├─ models/                 # SQLAlchemy Models（19 张表）
│  ├─ schemas/                # Pydantic Schemas（驼峰输出）
│  ├─ api/(auth,dashboard,cars,market,sales,recommendations,predictions,sentiment,admin)
│  ├─ services/               # 业务聚合（销量预测/推荐/舆情）
│  ├─ crawlers/               # 数据采集（乘联会/工信部/模板解析）
│  ├─ analysis/               # 算法模型（时序预测/评分）
│  ├─ database/(session,base) # 数据库会话
│  └─ utils/                  # 工具函数
├─ scripts/(seed_demo.py,collect_data.py,clean_data.py,import_data.py,train_prediction.py)
├─ data/(raw/ cleaned/ processed/)
├─ alembic/                   # 数据库迁移
├─ tests/                     # 契约测试（与 Mock 响应比对）
├─ requirements.txt
├─ .env.example
└─ README.md
```

## 快速开始

### 1. 创建数据库

```sql
CREATE DATABASE car2026 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，修改 DATABASE_URL 与 SECRET_KEY
```

### 4. 初始化数据库与种子数据

```bash
# 创建所有表
alembic upgrade head

# 导入品牌、地区、演示账号
python scripts/seed_demo.py
```

### 5. 启动服务

```bash
python -m uvicorn app.main:app --reload --port 8000
```

访问 http://localhost:8000/docs 查看 API 文档。

### 6. 前端对接

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

- 全部 49 条路由与前端 `src/mock/handlers.ts` 完全一致
- 统一响应外壳：`{ code: 0, message: "", data, timestamp }`
- 业务错误：HTTP 200 + `code != 0`（前端按 envelope 处理）
- 未认证：HTTP 401（前端自动登出）
- 字段驼峰输出：Pydantic `alias_generator=to_camel`

### 数据来源

| 数据 | 首选来源 | 备注 |
|---|---|---|
| 品牌清单 | 品牌官网/中汽协 | 静态维表 |
| 车型参数 | 工信部《免征车辆购置税新能源汽车车型目录》 | 续航/电池/功率最权威 |
| 月销量 | 乘联会/中汽协公开快讯 | 优先厂商排名快讯 |
| 地区销量 | 乘联会公开摘要 | 缺失时按份额分布估算并标注 |
| 评价 | 汽车之家/懂车帝（robots.txt 允许时） | 否则手动整理 CSV 导入 |

**原则**：拿不到则留空并记录 `source=unavailable`，绝不编造；采集前检查 robots.txt 与 ToS。

## 开发

### 添加新的数据库迁移

```bash
alembic revision -m "描述"
# 编辑 alembic/versions/xxxxx_描述.py
alembic upgrade head
```

### 采集数据

```bash
# 采集乘联会快讯（限月频）
python scripts/collect_data.py --source cpca --period 2026-08

# 手动导入 CSV
python scripts/import_data.py --file data/cleaned/cars_2026-08.csv
```

### 训练预测模型

```bash
python scripts/train_prediction.py --car-id 1 --horizon 6
```

## 测试

```bash
pytest tests/ -v
```

契约测试：把前端 Mock 响应固化为 JSON 快照，逐字段比对真实 API。

## 部署

- 环境：生产环境 `APP_ENV=production`，修改 `SECRET_KEY`
- 数据库：使用读写分离或连接池配置
- 运行：`uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4`

## 许可

MIT

---

**仓库**: https://github.com/gfy200627-dot/car2026-backend
**前端**: https://github.com/gfy200627-dot/car2026