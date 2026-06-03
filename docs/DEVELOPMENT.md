# Development

## 环境要求

- Python 3.11 或更新版本
- `pip`
- SQLite
- 本地 Chromium，用于需要浏览器会话的采集任务
- JavaScript runtime，用于 `pyexecjs` 驱动的 Douyin 签名

依赖文件：

```text
requirements.txt
```

主要运行依赖：

- FastAPI
- Uvicorn
- NetworkX
- pyvis
- httpx
- Playwright
- pyexecjs
- xhshow

## 安装步骤

如果当前 Python 环境允许 pip 安装：

```bash
cd OSGE
python -m pip install -r requirements.txt
```

在 Debian、Raspberry Pi OS 等启用 PEP 668 的系统上，系统 Python 可能禁止直接 pip 安装依赖。此时使用虚拟环境或其他已管理的 Python 环境：

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

OSGE 运行时不强制虚拟环境。关键是运行命令所用的 Python 已安装 `requirements.txt` 中的依赖。未激活虚拟环境时，CLI 命令可用 `.venv/bin/python ...`，服务脚本可设置 `OSGE_PYTHON=.venv/bin/python`。

如需要 Playwright 管理的浏览器：

```bash
python -m playwright install
```

当前 OSGE 也可复用系统 Chromium。默认 CDP profile：

```text
${XDG_CACHE_HOME:-$HOME/.cache}/osge-chromium
```

不要把 Chromium profile、cookies、日志中的账号信息或平台响应提交到仓库。

## 数据库初始化

```bash
python scripts/init_db.py
```

指定数据库路径：

```bash
python scripts/init_db.py --db data/database/osge_overlay.db
```

schema 定义在：

```text
core/db.py
```

## 运行方式

启动本地 Web 服务：

```bash
scripts/osge_service.sh start
```

服务脚本默认使用当前环境变量 `PATH` 中的 `python`，并通过 `python -m uvicorn` 启动服务。需要指定解释器或 uvicorn 命令时，可设置：

```bash
OSGE_PYTHON=/path/to/python OSGE_UVICORN=/path/to/uvicorn scripts/osge_service.sh start
```

未激活虚拟环境但需要使用其中依赖时，只指定 Python 即可：

```bash
OSGE_PYTHON=.venv/bin/python scripts/osge_service.sh start
```

查看状态：

```bash
scripts/osge_service.sh status
```

停止服务：

```bash
scripts/osge_service.sh stop
```

默认页面：

```text
http://127.0.0.1:8010/graph
```

健康检查：

```text
http://127.0.0.1:8010/api/health
```

## 常用开发命令

构建边：

```bash
python scripts/build_edges.py --db data/database/osge_overlay.db
```

分析图谱：

```bash
python scripts/analyze_graph.py --db data/database/osge_overlay.db
```

渲染图谱：

```bash
python scripts/render_graph.py \
  --db data/database/osge_overlay.db \
  --platform xiaohongshu \
  --output data/processed/osge_graph.html
```

展开一个 Xiaohongshu 账号：

```bash
python scripts/expand_account.py \
  --platform xiaohongshu \
  --db data/database/osge_overlay.db \
  --account xiaohongshu:<profile_id> \
  --max-notes 5 \
  --max-comments 10
```

展开一个 Douyin 账号：

```bash
python scripts/expand_account.py \
  --platform douyin \
  --db data/database/osge_overlay.db \
  --account douyin:<sec_uid> \
  --max-notes 5 \
  --max-comments 10
```

刷新单帖评论：

```bash
python scripts/refresh_comments_minimal.py \
  --platform xiaohongshu \
  --post-id <platform_post_id> \
  --max-comments 10
```

如果某个平台的评论接口需要额外上下文，可用 `--comment-context key=value` 传入；该参数可重复。

`--force` 只用于有意重新观察已知评论或回复的调试场景。

## 多平台接入

新增平台应接入现有 adapter 类型和 registry，不为单个平台新增独立 runner、Web API 分支或前端硬编码。

### 接口类型

平台接入分为三类接口。

#### 标准记录

标准记录定义在 `adapters/base.py`：

- `AccountRecord`
- `PostRecord`
- `CommentRecord`
- `CommentCrawlResult`
- `PlatformAdapter`

平台原始响应只在 adapter 内解析。进入 core 层前必须映射为这些标准记录。

`PostRecord.platform_context` 用于保存同一平台后续评论请求所需的运行期上下文。core 层只透传，不解释其中的 key。

#### Adapter 方法

当前采集链路使用 `MinimalCommentAdapter` + `PlatformAdapter`。新增平台 adapter 至少提供：

```python
platform: str
index_url: str
cookie_urls: list[str]

async def fetch_profile(account_url: str) -> AccountRecord

async def fetch_posts(
    account_id: str,
    limit: int,
    *,
    platform_context: Mapping[str, str] | None = None,
) -> list[PostRecord]

async def fetch_comments(
    post_id: str,
    limit: int,
    *,
    platform_context: Mapping[str, str] | None = None,
    get_sub_comments: bool = False,
    known_comment_ids: set[str] | None = None,
) -> CommentCrawlResult
```

通用 expansion runner 复用同一个浏览器 session，因此当前 adapter 还需要提供 session 级方法：

```python
async def fetch_profile_in_session(session: BrowserSession, account_url: str) -> AccountRecord

async def fetch_posts_in_session(
    session: BrowserSession,
    account_id: str,
    limit: int,
    *,
    platform_context: Mapping[str, str] | None = None,
) -> list[PostRecord]

async def fetch_comments_in_session(
    session: BrowserSession,
    post_id: str,
    limit: int,
    *,
    platform_context: Mapping[str, str] | None = None,
    get_sub_comments: bool = False,
    known_comment_ids: set[str] | None = None,
) -> CommentCrawlResult
```

如果某个平台不需要 `platform_context`，方法仍应接收该参数并忽略它。这样可以保持通用 runner 对所有平台使用同一调用方式。

`PlatformAdapter.fetch_interactions` 是未来直接互动记录 adapter 的预留接口。当前 profile/post/comment 采集主链路不依赖它。

#### Registry metadata

每个平台必须在 `adapters/registry.py` 注册 `PlatformDefinition`。

必填或常用字段：

- `platform_id`
- `display_name`
- `short_name`
- `base_url`
- `aliases`
- `url_markers`
- `adapter_factory`
- `normalize_profile_input`
- `context_from_url`
- `requires_comment_context`
- `log_prefix`
- `item_label`
- `id_label`
- `display_id_field_order`
- `expand_script`

`normalize_profile_input(value)` 返回：

```python
tuple[platform_user_id, profile_url]
```

`context_from_url(value)` 返回：

```python
dict[str, str]
```

如果评论接口依赖帖子级 token、source 或其他上下文，设置 `requires_comment_context=True`，并通过 `PostRecord.platform_context` 传给评论采集。

### 接入步骤

新增平台优先按以下顺序处理：

1. 在 `adapters/{platform}.py` 实现平台 adapter、client、parser 和必要 signer。
2. 把 profile、post、comment 映射为 OSGE 标准记录。
3. 如需要 JavaScript 签名资产，放到 `adapters/assets/{platform}.js`。
4. 在 `adapters/registry.py` 注册平台 metadata、adapter factory、profile 输入归一化和 UI metadata。
5. 让采集任务走 `core/platform_expansion_runner.py` 和 `scripts/expand_account.py --platform ...`。
6. 避免在 `web/app.py`、`core/graph_assets/` 或脚本中新增平台专用分支。
7. 用低采集上限验证 profile、post、comment、建边、分析和图谱渲染。

## 测试方式

当前仓库没有测试目录，也没有完整自动化测试套件。新增测试后建议使用 `pytest`：

```bash
python -m pytest
```

当前可用的轻量检查：

```bash
python -m compileall adapters core web scripts
node --check core/graph_assets/network_bootstrap.js
python scripts/init_db.py
python scripts/build_edges.py --db data/database/osge_overlay.db
python scripts/analyze_graph.py --db data/database/osge_overlay.db
python scripts/render_graph.py --db data/database/osge_overlay.db
```

可用临时数据库做 dry-run 类检查，避免触发真实采集。

## 常见问题

### 服务启动后会自动采集平台数据吗？

不会。Web 服务启动只提供本地页面和 API。平台采集需要操作者显式触发。

### Chromium CDP 什么时候启动？

默认延迟到采集任务需要时启动。设置 `OSGE_START_CDP=1` 可以在服务启动时预启动。

### 没有拿到 profile 时怎么办？

通常是当前 Chromium session 未登录，或平台验证、风控拦截了 profile 请求。打开当前 OSGE Chromium 窗口，进入对应平台完成登录或验证，确认页面可访问后重试采集。

### 采集是否依赖外部项目？

默认链路是 OSGE 自有最小 adapter，数据写入 OSGE overlay 数据库。部分平台签名实现依赖第三方包或资产，应在许可和第三方声明中单独记录。

### 图节点表示真实个人吗？

不表示。默认图节点是平台账号。身份容器只是内部管理结构，不是实名识别结论。

### 隐藏账号会删除数据库记录吗？

对 OSGE-collected minimal data，隐藏和清理应使用 `hidden_at`、`hidden_reason` 等隐藏标记。数据行保留在本地数据库中。
