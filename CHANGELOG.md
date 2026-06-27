# Changelog

晨序的版本变更记录从飞书产品化改造开始重新维护。

格式参考 [Keep a Changelog](https://keepachangelog.com)，版本号遵循
[SemVer](https://semver.org)。

## [Unreleased]

### Changed

- 清理仓库展示、贡献说明、容器镜像和 Helm 元信息中的旧产品命名。
- 新增 `NOTICE`，明确说明项目来源、授权归属和当前独立产品定位。

## [0.1.0] - 2026-06-27

### Added

- 飞书长连接事件接收。
- 飞书机器人私聊收集成员进度。
- AI 整理成员回复，并在成员确认后写入数据库。
- 数据看板、收集进度、定时发布、集成设置、Skills 和管理页面。
- 管理页面支持进度记录筛选、新建、编辑和按日期维护。
- DeepSeek 与 OpenAI-compatible AI 配置。
- 定时发布任务可按时间、成员、项目范围发布进度快照。

### Changed

- 产品从原始站会机器人改造为飞书优先的团队进度工作流系统。
- Dashboard 导航聚焦数据看板、收集进度和定时发布三条核心链路。
- 进度数据模型收敛为项目、成员、岗位、进度内容、进度日期和更新时间。

[Unreleased]: https://github.com/Jobo16/morgenruf/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Jobo16/morgenruf/releases/tag/v0.1.0
