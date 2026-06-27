# 晨序

<p align="center">
  <img src="./app/src/static/logo.png" alt="晨序" width="180" />
</p>

<p align="center">
  <strong>面向团队进度收集、确认、看板和定时发布的自托管工作流系统。</strong>
</p>

<p align="center">
  <a href="https://github.com/Jobo16/chenxu/actions/workflows/test.yml"><img src="https://github.com/Jobo16/chenxu/actions/workflows/test.yml/badge.svg" alt="Tests" /></a>
  <a href="https://github.com/Jobo16/chenxu/actions/workflows/lint.yml"><img src="https://github.com/Jobo16/chenxu/actions/workflows/lint.yml/badge.svg" alt="Lint" /></a>
  <a href="https://github.com/Jobo16/chenxu/actions/workflows/docker.yaml"><img src="https://github.com/Jobo16/chenxu/actions/workflows/docker.yaml/badge.svg" alt="Docker" /></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/Feishu-long%20connection-00B96B" alt="Feishu long connection" />
  <img src="https://img.shields.io/badge/AI-DeepSeek%20%7C%20OpenAI-1AA7EC" alt="AI providers" />
</p>

晨序把日常进度收集拆成两条清晰链路：机器人私聊成员收集并确认进度，Dashboard 负责查看、修正、追溯和发布快照。它适合公司内部自建使用，默认支持飞书长连接，本地测试不需要公网回调。

## 产品截图

![数据看板](./docs/images/dashboard.png)

![收集进度](./docs/images/collections.png)

![定时发布](./docs/images/publish.png)

## 产品能力

- 通过飞书机器人向指定成员私聊收集进度，避免采集群聊噪音。
- AI 将成员回复整理为结构化进度，并要求成员确认后入库。
- 数据模型围绕项目、成员、岗位、进度内容、进度日期和更新时间。
- Dashboard 首屏是数据看板，支持项目、成员和时间维度查看。
- 管理页面支持筛选、手动新建、编辑进度记录，并保留修改快照。
- 定时发布可以把指定时间、成员、项目范围的进度快照发到飞书群或 Webhook。
- AI 汇总仅用于发布开头摘要，主要明细来自数据库，减少幻觉影响。
- 支持 DeepSeek 与 OpenAI-compatible 接口，DeepSeek 只需配置 Base URL、模型和 Key。

## 界面结构

核心导航：

- `数据看板`：查看团队进度概览、项目分布、成员分布和最近进度。
- `收集进度`：配置飞书私聊收集任务、参与成员、工作日和提醒内容。
- `定时发布`：配置进度快照的定时推送目标、范围和 AI 摘要。

辅助导航：

- `集成设置`：配置飞书长连接、默认群聊、管理员、AI 服务和 Key。
- `Skills`：下载最新 Skills 包。
- `管理页面`：维护进度记录、成员信息和项目信息。

## 快速启动

### 1. 准备环境

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+
- 飞书自建应用，启用机器人能力和事件长连接

### 2. 配置环境变量

```bash
cd app
cp .env.example .env
```

最小飞书配置：

```env
DATABASE_URL=postgresql://chenxu:chenxu@localhost:5432/chenxu
FLASK_SECRET_KEY=replace-with-a-random-secret
APP_URL=http://localhost:3000
DASHBOARD_AUTH=none

FEISHU_EVENT_MODE=ws
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=
FEISHU_TEAM_ID=feishu
FEISHU_TEAM_NAME=你的公司

FEISHU_AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

长连接模式不需要配置飞书公网回调地址、`Verification Token` 或 `Encrypt Key`。如果要限制 Dashboard 访问，把 `DASHBOARD_AUTH` 改为 `key` 并设置 `DASHBOARD_ADMIN_KEY`。

### 3. 启动后端

```bash
cd app
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python src/migrate.py
python src/main.py
```

访问：

```text
http://localhost:3000/dashboard
```

### 4. 构建前端

修改 Dashboard 前端后执行：

```bash
cd app/frontend
npm install
npm run build
```

构建产物会写入 `app/src/static/dashboard/`，由 Flask/Gunicorn 直接提供。

## 飞书应用配置

在飞书开放平台创建自建应用后，至少需要：

- 启用机器人能力。
- 事件订阅选择“使用长连接接收事件”。
- 订阅消息事件 `im.message.receive_v1`。
- 开通机器人发消息能力。
- 如需从 Dashboard 同步群聊成员，开通读取通讯录或群成员所需权限。

启动后进入 `集成设置`：

1. 填写 `App ID` 和 `App Secret`。
2. 事件接收选择 `长连接`。
3. 点击 `连接飞书` 同步群聊和成员。
4. 选择默认群聊和管理员。
5. 配置 DeepSeek 或 OpenAI Key。

## AI 整理流程

成员回复进度后，晨序会把以下上下文交给 AI：

- 成员原始回复和补充对话。
- 数据库中已有项目名。
- 成员名称、岗位标签。
- 该成员上一次提交的进度。

AI 必须返回内部 JSON：`project_name`、`role`、`content`。系统会校验项目名是否存在、内容是否为空，再把人类可读的预览发给成员确认：

```text
项目：晨序
岗位：后端
进度：
完成飞书长连接收集链路。
下一步验证 Dashboard 历史记录。
```

成员回复 `确认` 后才会入库；如果内容不准确，成员继续补充，系统会重新整理。

## 数据与安全

- 飞书事件默认走长连接，不要求本地开发暴露公网回调。
- App Secret、AI Key、Dashboard Key 不会在设置接口中明文返回。
- Dashboard 手动修改进度会生成快照，便于追溯和回滚。
- 进度发布明细来自数据库查询，AI 只生成摘要文本。
- 建议生产环境使用 PostgreSQL、Redis 和 `DASHBOARD_AUTH=key`。

## 项目结构

```text
chenxu/
├── app/
│   ├── src/                  # Flask 后端、飞书长连接、调度、Dashboard API
│   ├── frontend/             # React Dashboard 源码
│   ├── migrations/           # SQL 迁移
│   ├── tests/                # Python 测试
│   ├── docker-compose.yml    # 本地自托管启动配置
│   └── requirements.txt
├── .github/                  # CI、Issue、PR 模板
├── README.md
└── LICENSE
```

## 常用命令

```bash
# 后端测试
uv run --with-requirements app/requirements.txt --with pytest --isolated python -m pytest app/tests -q

# 前端构建
cd app/frontend && npm run build

# 数据库迁移
cd app && ./.venv/bin/python src/migrate.py

# 本地服务
cd app && ./.venv/bin/python src/main.py
```

## 许可证

[MIT](./LICENSE)。项目来源和授权归属见 [NOTICE](./NOTICE)。
