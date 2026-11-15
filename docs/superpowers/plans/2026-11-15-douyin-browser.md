# Douyin Browser Fallback Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task.

**Goal:** 在 1.2.0-beta 上修复抖音风控回退和卡片底部留白。
**Architecture:** HTTP 解析保留，失败后由独立浏览器模块启动正常访客会话，观察并校验站点的详情响应。卡片按主体高度输出。
**Tech Stack:** Python 3.10+、aiohttp、Chromium CDP、Pillow。
**Spec:** `docs/superpowers/specs/2026-11-15-douyin-browser-design.md`

## Global Constraints

- 基线为 dev/c9917ed；用户指定版本 1.2.1；无新增 Python 依赖。
- 浏览器会话串行、30 秒上限，关闭隔离临时目录内的实例，不接触用户账号。
- 仅接收固定抖音详情接口和正确作品 ID；不手工构造新的风控签名。

## Review Focus

错误作品响应、JSON 损坏、浏览器缺失、超时或取消留下进程、HTTP 正常时额外启动浏览器。

## Task 1: 浏览器回退与分享页错误处理

Files: create `core/parser/platform/douyin_browser.py`; modify `douyin.py`, `douyin_web.py`, `core/config_manager.py`, `_conf_schema.json`; tests `tests/test_douyin.py`, `tests/test_douyin_browser.py`。

- [x] 写回归测试，验证验证码触发回退、正确作品数据合并、错误 ID 拒绝、正常响应不启动浏览器、重试上限。
- [x] 运行测试确认当前 beta 失败。
- [x] 实现 `DouyinBrowserClient.fetch_detail(item_id, media_type) -> tuple[dict, str]`、30 秒边界与进程清理；配置开关和路径。
- [x] 验证详情事件过滤、损坏 JSON、取消与超时关闭浏览器；运行完整单测。

## Task 2: 卡片边界、版本与交付

Files: `core/rika_render/render.py`, `tests/test_card_edges.py`, version metadata, README, CHANGELOG。

- [x] 用四种布局、两种主题、有无封面检查底边 alpha，确认旧代码失败。
- [x] 移除额外高度并更新缓存版本，验证全部场景通过。
- [x] 更新 1.2.1 版本与浏览器环境说明。
- [ ] 对原始短链执行一次完整解析并读取媒体前缀；编译、配置与全量测试通过后独立审查、推送修复分支，PR 目标 dev。

## 执行记录

- 用户指定版本从计划中的 beta.1 调整为 1.2.1。
- 最终 79 项单测、编译、配置与格式检查通过。真实链接和媒体前缀结果见 `docs/validation/2026-11-15-v1.2.1.md`。
- 审查发现清理期间的取消窗口；回归测试先失败，增加 shield 清理任务后通过，独立复核确认可推送。
