# Contributing to 晨序

晨序是面向飞书的自托管团队进度工作流系统。欢迎提交 Bug、改进建议、
文档修正和实现代码。

## 本地开发

```bash
git clone https://github.com/Jobo16/chenxu
cd chenxu

cd app
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python src/migrate.py
python src/main.py
```

Dashboard 地址：

```text
http://localhost:3000/dashboard
```

如需测试完整飞书链路，请在 `.env` 或 Dashboard 的集成设置中配置
`FEISHU_APP_ID`、`FEISHU_APP_SECRET`，事件接收方式选择长连接。

## 项目结构

```text
app/
  src/          Flask 后端、飞书长连接、Dashboard API
  frontend/    React Dashboard 源码
  migrations/  SQL 迁移
  tests/       Python 测试
  helm/        Kubernetes Helm chart
```

## 代码规范

- 新代码优先服务当前产品形态，不为旧平台行为增加兼容层。
- 保持实现直接、清晰，避免无实际收益的抽象。
- 不提交密钥、Token、真实 App Secret 或内部群聊/成员 ID。
- Dashboard 变更需要保持极简中文界面，避免无功能价值的说明文案。

## 提交 PR

1. 从 `main` 创建分支。
2. 保持提交聚焦，提交信息使用 Conventional Commits。
3. 涉及功能变更时补充测试或说明本地验证路径。
4. 打开 PR，按模板填写测试结果和截图。

常用提交示例：

```text
feat: add publish job filters
fix: collect only confirmed feishu dm replies
docs: update feishu setup guide
chore: refresh helm metadata
```

## 运行测试

```bash
uv run --with-requirements app/requirements.txt --with pytest --isolated python -m pytest app/tests -q
```

前端构建：

```bash
cd app/frontend
npm install
npm run build
```

## 报告问题

请使用 GitHub Issue 模板，并包含复现步骤、预期行为、实际行为、部署方式和相关日志。

## 许可证

贡献代码默认按 [MIT License](LICENSE) 授权。项目来源和版权说明见 [NOTICE](NOTICE)。
