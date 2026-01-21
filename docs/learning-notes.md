# HelloAgents Trip Planner 学习拆解（FastAPI / Agent Tool Calling / MCP）

> 定位：这是你的第二个 Agent 项目，用来补齐“**后端 FastAPI 工程化** + **Agent 工具调用（tool calling）** + **MCP Server 接入**”这条链路。
> 你已有“多智能体会诊 + RAG”项目，本项目更偏：**工具生态 / 外部能力接入 / Web API 产品化**。

---

## 1. 项目目标与最小闭环

**最小闭环（从用户点击到拿到结果）**：
1) 前端页面提交旅行需求（城市/日期/偏好…）
2) 后端 FastAPI 接收请求并调用多智能体 `plan_trip`
3) 多个 Agent 通过 MCP 工具调用高德地图：搜景点 / 查天气 / 搜酒店
4) Planner Agent 汇总信息并输出严格 JSON
5) 后端解析 JSON → Pydantic 校验 → 返回给前端展示

你可以用一句话描述：
> “把 LLM 变成一个会自动调用高德地图工具的旅行规划 Agent，并提供 FastAPI API 给前端使用。”

---

## 2. 后端 FastAPI：结构与关键点

### 2.1 入口与生命周期
- 入口文件：backend/app/api/main.py
  - 创建 `FastAPI()`（title/version/description/docs_url）
  - 配置 `CORSMiddleware`（允许前端跨域）
  - `startup_event()`：打印配置并 `validate_config()` 校验环境变量
  - 注册路由：`/api/trip`、`/api/poi`、`/api/map`
- 启动脚本：backend/run.py
  - `uvicorn.run("app.api.main:app", reload=True)`

你在面试里可以强调：
- “把配置校验放在 startup，避免服务启动后才报错。”
- “用 CORS origin 白名单让前端开发可用。”

### 2.2 配置与环境变量
- 配置管理：backend/app/config.py
  - `Settings(BaseSettings)` 读取 `.env`
  - 同时尝试加载上层 `HelloAgents/.env`（如果存在）
  - `validate_config()`：强制要求 `AMAP_API_KEY`，LLM key 给 warning（不阻断）

**你真正需要关注的 env**：
- `AMAP_API_KEY`：高德 MCP 工具运行必需
- `LLM_API_KEY` / `OPENAI_API_KEY`：HelloAgentsLLM 读取
- `LLM_BASE_URL`、`LLM_MODEL_ID`：对接不同供应商（如 DashScope compatible-mode）
- `CORS_ORIGINS`：前端地址

### 2.3 路由与数据模型
- Pydantic 模型：backend/app/models/schemas.py
  - 请求：`TripRequest` / `RouteRequest` / `POISearchRequest`
  - 响应：`TripPlanResponse` / `WeatherResponse` 等
  - 重点：`TripPlan` 是最终输出 schema（days/attractions/meals/hotel/weather/budget）

- 旅行规划路由：backend/app/api/routes/trip.py
  - POST `/api/trip/plan`：调用 `get_trip_planner_agent().plan_trip(request)`

- 地图服务路由：backend/app/api/routes/map.py
  - GET `/api/map/poi`、GET `/api/map/weather`、POST `/api/map/route`
  - 实际调用 `AmapService`（MCPTool.run 调用具体 tool）

- POI 路由：backend/app/api/routes/poi.py
  - GET `/api/poi/detail/{poi_id}`：高德 POI 详情
  - GET `/api/poi/photo`：Unsplash 图片（可选增强，不是 MCP）

**重要工程点**：
- 路由函数是 `async`，但内部很多调用是同步 `.run()` 或 requests；真正生产要进一步异步化或队列化（你可以在学习笔记里记录为“后续优化点”）。

---

## 3. Agent 协作 + tool calling：怎么组织的

核心文件：backend/app/agents/trip_planner_agent.py

### 3.1 Agent 角色拆分
这里是一个“多智能体流水线”而不是开放式对话：
- 景点搜索 Agent：只负责调用 `maps_text_search`
- 天气 Agent：只负责调用 `maps_weather`
- 酒店 Agent：只负责调用 `maps_text_search`（关键词=酒店）
- Planner Agent：不调用工具，只负责把上面的结果整合成严格 JSON

对应代码结构：
- `MultiAgentTripPlanner.__init__()`：创建 1 个共享 `MCPTool`，然后把它 add_tool 给 3 个 Agent
- `plan_trip()`：按步骤串联：景点→天气→酒店→规划→解析

你可以把它解释成：
> “把复杂任务拆成可工具化的子任务，每个子 Agent 的 prompt 强约束‘必须调用工具’，最后由 Planner 做结构化汇总。”

### 3.2 tool calling 的实现方式（这里很值得你讲清楚）
这个项目里出现了两种“工具调用”路径：

**路径 A：Agent 侧调用（LLM 生成 tool call，框架执行）**
- 在 prompt 里约束输出类似：
  - `[TOOL_CALL:amap_maps_text_search:keywords=公园,city=上海]`
  - `[TOOL_CALL:amap_maps_weather:city=北京]`
- `SimpleAgent.run()` 生成这段文本，HelloAgents 解析并触发 `MCPTool` 执行

**路径 B：后端服务侧调用（代码直接 call_tool）**
- 在 backend/app/services/amap_service.py 里：
  - `self.mcp_tool.run({"action":"call_tool","tool_name":"maps_weather", ...})`

面试时你可以说：
- “我既支持 Agent 自主工具调用（更像 agentic），也保留后端直接调用工具作为确定性 API（更像传统后端服务层）。”

### 3.3 输出结构化与容错
- Planner Agent prompt 强制输出 JSON
- `_parse_response()`：从 markdown code block 或纯文本中抓 JSON
- 如果解析失败：`_create_fallback_plan()` 兜底（返回一个可用的结构化结果）

这里你能强调：
- “结构化输出需要**解析策略 + 兜底策略**，否则前端展示会崩。”

---

## 4. MCP Server：它是什么、你怎么接入的

### 4.1 MCP 在这项目里的位置
MCP（Model Context Protocol）在这里充当“工具服务器协议层”：
- LLM/Agent 不直接打高德 HTTP API
- 而是通过 MCP Server 暴露标准化 tool（`maps_text_search`/`maps_weather`/路线规划等）

### 4.2 MCPTool 的关键配置
在 agent 和 amap_service 里创建 MCPTool：
- `server_command=["uvx","amap-mcp-server"]`
- `env={"AMAP_MAPS_API_KEY": settings.amap_api_key}`
- `auto_expand=True`

`auto_expand=True` 的含义（面试会问）：
- MCP server 提供一堆工具
- auto_expand 会把这些工具“展开”为可被 Agent 直接调用的工具列表（而不是一个总入口）

### 4.3 可用工具与调用名
从代码可以看到典型工具名：
- `maps_text_search`
- `maps_weather`
- `maps_direction_walking_by_address`
- `maps_direction_driving_by_address`
- `maps_direction_transit_integrated_by_address`
- `maps_geo`
- `maps_search_detail`

你要能解释：
- “这些名字来自 MCP server 的 tool schema，MCPTool 会拉取并暴露。”

---

## 5. 前后端如何对接（你可以简要了解）

前端请求封装：frontend/src/services/api.ts
- `POST /api/trip/plan` → 生成旅行计划
- `VITE_API_BASE_URL` 默认 `http://localhost:8000`

后端 CORS 默认允许 localhost:5173，所以开发时前后端分离能直接跑。

---

## 6. 你可以怎么把它写成“第二项目”的亮点

建议你在简历/面试里把它从“旅行规划 Demo”提炼成工程点：
- FastAPI：路由分层 + Pydantic schema + startup 配置校验 + CORS
- Agent 工具调用：多 Agent 分工、prompt 强约束工具调用、结构化 JSON 输出与解析容错
- MCP：用 MCPTool 接入第三方工具服务器（高德地图），同时支持“Agent 自主调用”和“后端服务直接调用”两种路径

一句话模板（偏岗位 JD）：
> “基于 FastAPI 搭建 Agent 服务端，使用 HelloAgents 的 MCPTool 接入高德地图 MCP Server，实现多智能体自动工具调用（景点/天气/酒店）与结构化行程生成，并提供标准 REST API 给前端消费。”

---

## 7. 可继续优化点（可选，面试加分）

- **异步化/并发**：景点/天气/酒店三步可以并行（async + gather），降低总延迟
- **解析与数据落库**：把 MCP 返回结果解析成强类型（`POIInfo/WeatherInfo`），而不是当前的 TODO 空 list
- **缓存**：天气/POI 可以做 TTL cache；相同城市/日期命中率高
- **可观测性**：请求链路 id、耗时分段（LLM、MCP、解析）
- **安全**：隐藏 key、限制 tool 调用参数、设置超时/重试

---

## 8. 你学习这个项目的建议顺序（最省时间）

1) 跑通：启动后端、前端，确保 `/docs` 能打开
2) 读入口：main.py 看路由注册与 startup
3) 读 Agent：trip_planner_agent.py 看“工具调用格式”和 4 步 pipeline
4) 读 MCP：amap_service.py 看 MCPTool 如何 call_tool
5) 读 schemas：确认 JSON 输出结构与前端渲染依赖

---

如果你希望我再把这份笔记“写得更像面试讲稿”，我可以再补一页：
- 30 秒版本（电梯陈述）
- 2 分钟版本（含调用时序）
- 高频追问（MCP vs function calling、auto_expand 是什么、怎么做容错/并发/缓存）
