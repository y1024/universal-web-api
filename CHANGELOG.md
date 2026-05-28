# 更新日志

## 2026-05-28

new:
- 新增 `/v1/responses` 兼容入口，允许只支持 Responses wire API 的 Codex 直接接入当前项目。

change:
- Responses 请求现在会复用现有 `/v1/chat/completions` 执行链，并把 `input`、`instructions`、`tools`、`tool_choice`、`text.format` 等字段转换为现有聊天请求格式。
- Responses 流式模式改为输出 `response.created`、`response.output_item.added`、`response.output_text.delta`、`response.function_call_arguments.done`、`response.completed` 等 SSE 事件，方便 Codex 按 Responses 协议消费。
- Responses 工具调用流补充 `response.function_call_arguments.delta`、`response_id` 和 in-progress 到 done 的事件过渡，工具调用历史里的 `function_call_output` 也会更准确地转回现有工具结果消息。
- `/v1/models` 现在会同时兼容 OpenAI 和 Anthropic/Claude Code 风格：接受 `Authorization` 或 `x-api-key` 认证，并在携带 `anthropic-version` 头时返回 Anthropic 风格模型列表。
- Claude/Anthropic 兼容层现在会把非流式错误转换为 Anthropic 风格错误体，并为 `/v1/messages`、`/v1/messages/count_tokens` 与流式响应补充 `request-id` 头，便于 Claude Code 网关诊断。

fix:
- 修复项目仅暴露 `/v1/chat/completions` 时无法直接作为 Codex provider 使用的问题。

## 2026-05-23

fix:
- 工具调用校验模块补全参数长度限制辅助函数导入，修复 `_get_max_tool_argument_chars` 缺失导致的 `tool_calling_failed`。
- 工具调用 XML 解析模块补全 adapter / legacy 标签常量导入，修复 `_PREFERRED_XML_WRAPPER_TAG` 等缺失名称导致的运行时崩溃。
- 工具调用提示词模块补全 `Tuple` 类型导入，避免运行时解析类型注解时触发 `NameError`。
- 工具调用 JSON 解析与校验逻辑现在会正确接受 `{"content":"...","tool_calls":[]}` 这类结构化最终回复，不再误判为畸形工具载荷并进入多轮内部重试。

## 2026-05-22

fix:
- 自动更新恢复默认 TLS 证书链与主机名校验，移除宽松 SSL 下载逻辑，降低更新链路被中间人劫持的风险。
- 自动更新在合并 `sites.json` / `commands.json` 时，配置解析失败不再按空配置继续覆盖，避免异常情况下清空本地数据。
- 自动更新前新增项目快照备份与失败回滚，覆盖核心代码与静态资源，降低解压或写入中断导致的不可恢复损坏。
- 标签页池的全局网络监听停止流程避开持锁等待，减少监听线程退出时拖住整个池管理器的卡死风险。
- 标签页池为会话增加最后已知 URL 缓存，后台健康检查与孤立上下文探测在 `BUSY` 状态下不再并发读取 `tab.url`，降低 CDP / WebSocket 冲突概率。
- 过期的孤立浏览器上下文现在会在宽限期后主动释放，不再只从 orphan 记录中移除，减少 Chrome 后台上下文泄漏。
- DOM 模式下移除与前台轮询并发的 event-only 网络监听线程，避免同一 DrissionPage/CDP 连接被多线程同时使用。
- 插件市场路由把同步阻塞调用切到 FastAPI 线程池，减少事件循环被同步网络 I/O 卡住的问题。
- 工具调用解析与校验补全缺失导入，修复 `html.unescape`、`math.isfinite`、`math.isclose` 及参数修复/深度限制路径上的运行时崩溃。

## 2026-05-21

new:
- 函数调用新增两个可选开关：预填充乱序零宽、注入预填充/尾部提示词。
- 函数调用的额外预填充与尾部提示词支持随机乱序和零宽字符注入。

change:
- 设置面板和环境配置 schema 已同步新增上述两个开关。
- 函数调用提示词拼装逻辑已按开关拆分，关闭注入后只保留重试策略提示词。
- 教程页补充了这两个开关的说明。

fix:
- 刷新前端脚本版本号，避免浏览器继续加载旧版设置页。
