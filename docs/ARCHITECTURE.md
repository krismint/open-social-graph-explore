# Architecture

## 概览

OSGE 是本地优先的社交关系图谱研究工具。当前主线围绕平台账号构图，不把账号自动等同为真实个人。

```text
Data Source
  -> Platform Adapter
  -> Storage
  -> Graph Builder
  -> Analysis Engine
  -> Visualization
```

## 系统模块

### Platform Adapter

职责：

- 识别平台输入
- 复用本地 Chromium CDP 会话
- 读取公开可访问或已授权字段
- 处理平台请求、签名、分页和解析
- 把平台返回映射为 OSGE 标准记录

当前实现：

- `adapters/registry.py`：平台 registry，定义平台 id、别名、URL markers、adapter factory、profile 归一化、前端 UI metadata
- `adapters/base.py`：`AccountRecord`、`PostRecord`、`CommentRecord` 和 adapter protocol
- `adapters/minimal_platform.py`：共享 CDP session、profile 失败提示、评论去重 helper 和平台最小 adapter 基类
- `adapters/xiaohongshu.py`：Xiaohongshu client、签名封装、解析和 adapter
- `adapters/douyin.py`：Douyin client、签名封装、解析和 adapter
- `adapters/osge_http_clients.py`：平台无关 HTTP/session helper
- `adapters/assets/`：平台需要 JavaScript 签名资产时使用，例如 `douyin.js`

### Expansion Runner

职责：

- 准备采集目标
- 写入 crawl target 和 crawl job 状态
- 启动或复用 Chromium CDP
- 调用平台 adapter
- 同步 profile、post、comment 记录
- 建边、渲染图谱、完成 job 状态

当前实现：

- `core/platform_expansion_runner.py`：通用多平台采集编排
- `core/crawl_state.py`：采集目标、任务和历史状态
- `core/chromium_cdp.py`：本地 Chromium CDP 检测和启动

### Storage

职责：

- 保存平台账号、帖子、互动、派生边、证据、节点评分和采集状态

当前实现：

- 数据库：SQLite
- 默认路径：`data/database/osge_overlay.db`
- schema 入口：`core/db.py`
- 同步逻辑：`core/minicrawler.py`

### Graph Engine

职责：

- 从 `interactions` 聚合账号之间的关系边
- 保存边权重和证据

当前实现：

- 入口：`core/edge_builder.py`
- 规则：`core/scoring.py`
- 输出：`edges` 与 `evidences`
- 支持关系：comment、reply、repost、follow、mention

当前最小 adapter 主要写入评论和回复关系。

### Analysis Engine

职责：

- 计算图结构指标

当前实现：

- 入口：`core/graph_analyzer.py`
- 引擎：NetworkX
- 输出表：`node_scores`
- 指标：degree centrality、betweenness centrality、PageRank、community id、weighted degree

### Visualization

职责：

- 生成和服务本地图谱页面
- 提供节点搜索、采集提交、状态轮询、节点隐藏和相邻孤立节点清理

当前实现：

- 后端：FastAPI / Uvicorn
- 渲染：pyvis / vis-network
- Web 入口：`web/app.py`
- 图谱渲染：`core/graph_renderer.py`、`core/graph_render_*.py`
- UI 资产：`core/graph_assets/`
- 静态图谱输出：`data/processed/osge_graph.html`

图谱 UI 的平台列表、平台名称和输入提示来自 `adapters/registry.py` 注入的 metadata，不在前端资产中硬编码当前平台。

## 数据流

1. 操作者在本地 Web 页面或 CLI 中提交平台账号、主页 URL 或短链。
2. `adapters/registry.py` 根据 hint、前缀和 URL markers 判断平台。
3. `core/platform_expansion_runner.py` 归一化目标账号并创建 crawl job。
4. OSGE 检查或启动本地 Chromium CDP。
5. 平台 adapter 读取公开可访问或已授权字段，并返回标准记录。
6. `core/minicrawler.py` 写入 `accounts`、`posts` 和 `interactions`。
7. `core/edge_builder.py` 从互动记录聚合 `edges` 和 `evidences`。
8. `core/graph_analyzer.py` 计算节点指标并写入 `node_scores`。
9. `core/graph_renderer.py` 生成图谱 HTML。
10. FastAPI 服务 `/graph`、搜索、扩展任务和节点管理接口。

## 模块职责

| 模块 | 目录或文件 | 职责 |
| --- | --- | --- |
| Platform Registry | `adapters/registry.py` | 平台注册、识别、metadata、adapter factory |
| Platform Adapter | `adapters/{platform}.py` | 平台请求、签名、解析、标准记录映射 |
| Shared Adapter Flow | `adapters/minimal_platform.py` | CDP session、共享分页、profile/post/comment 接口 |
| Expansion Runner | `core/platform_expansion_runner.py` | 通用采集任务编排 |
| Storage | `core/db.py` | SQLite schema、迁移、默认连接 |
| Normalization | `core/normalizer.py`、`core/minicrawler.py` | 平台字段归一化和 overlay 同步 |
| Graph Builder | `core/edge_builder.py` | 互动到关系边的聚合 |
| Scoring | `core/scoring.py` | 关系类型规则和时间衰减 |
| Analysis | `core/graph_analyzer.py` | 网络指标计算 |
| Rendering | `core/graph_renderer.py`、`core/graph_render_*.py` | 图谱数据装配和 HTML 生成 |
| Web API | `web/app.py` | 本地服务、图谱页面、采集任务 API |
| CLI | `scripts/` | 初始化、构建、分析、渲染、扩展和服务管理 |

## 技术选型

| 类型 | 当前选型 | 说明 |
| --- | --- | --- |
| 数据库 | SQLite | 本地优先，便于研究和单机运行 |
| 图分析 | NetworkX | 计算中心性、PageRank、社区和 weighted degree |
| 后端 | FastAPI / Uvicorn | 本地图谱服务和任务 API |
| 可视化 | pyvis / vis-network | 生成交互式 HTML 图谱 |
| 浏览器会话 | Chromium CDP | 仅在采集任务需要时启动或复用 |
| HTTP | httpx | 平台 adapter 请求 |
| 签名依赖 | pyexecjs、xhshow | 当前 Douyin 和 Xiaohongshu adapter 使用 |
| 图数据库 | 未启用 | 未来可选 Neo4j、Memgraph 或其他图数据库 |

## 运行边界

- 正常服务启动不会主动采集平台数据。
- 采集任务由操作者显式触发。
- 默认采集限制保持保守。
- Chromium CDP profile 只作为本地会话复用，不应提交到仓库。
- 图谱节点是平台账号，不是已确认真实个人。
- 身份容器用于内部关联，不代表身份确认。
