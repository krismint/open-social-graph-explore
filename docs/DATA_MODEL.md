# Data Model

## 基本原则

OSGE 当前以平台账号构建图谱。`Account` 是默认图节点，`Identity` 是内部身份容器。自动创建的身份容器不是实名识别结果。

平台 adapter 必须把平台返回映射为 OSGE 标准记录，再交给 core 层入库。core 层不应直接依赖某个平台的原始响应结构。

## Adapter Records

标准记录定义在 `adapters/base.py`：

- `AccountRecord`
- `PostRecord`
- `CommentRecord`
- `CommentCrawlResult`
- `PlatformAdapter`

这些记录是 adapter 与 core 之间的边界。平台特有字段应尽量在 adapter 内消化；确实需要跨层传递时，使用 `platform_context` 这类平台上下文字典，不在通用 record 上增加具体平台字段。

`PostRecord.platform_context` 是运行期上下文，用于把某个 post 的后续评论请求所需信息传回同一平台 adapter。core 层只透传，不解释其中的 key。需要长期保存的平台上下文应另行设计 metadata 表或平台专属持久化策略。

## Node

### Person

概念层节点，当前不作为默认图节点。

未来只有在存在合法、明确、可记录的证据时，才可以把多个账号关联到同一个真实个人或实体。

### Identity

当前实现表：

- `identities`
- `identity_accounts`

用途：

- 保存内部身份容器
- 连接一个或多个平台账号
- 支持未来人工确认的跨平台关联

身份容器字段包括 `legal_name`、`phone`、`email`、`osge_account`、`display_name`、`notes`、`source`。这些字段不应由平台昵称自动填充为真实身份。

### Account

当前默认图节点。

实现表：`accounts`

关键字段：

- `account_id`：OSGE 账号节点 id，例如 `xiaohongshu:<profile_id>`
- `platform`：平台 id
- `platform_user_id`：平台内部 id 或采集 id
- `source_record_id`
- `username`
- `nickname`
- `profile_url`
- `avatar_url`
- `avatar_local_path`
- `bio`
- `location`
- `gender`
- `is_target`
- `crawl_level`
- `hidden_at`
- `hidden_reason`

平台昵称属于账号字段，不属于真实姓名。

### Post

实现表：`posts`

用途：

- 保存帖子、笔记或作品的最小上下文字段
- 作为评论、回复、转发等互动证据的来源上下文
- 为边权重计算提供评论数等上下文

关键字段：

- `post_id`
- `platform`
- `platform_post_id`
- `author_account_id`
- `content`
- `url`
- `created_at`
- `like_count`
- `comment_count`
- `repost_count`
- `source`

### Comment

当前不作为独立图节点持久化。

评论和回复以 `interactions` 记录保存，并通过 `source_record_id`、`parent_source_record_id`、`post_id`、`content`、`created_at` 等字段保留证据。

未来如需要评论级图谱，可把评论提升为独立节点。

## Edge

实现表：`edges`

边从 `interactions` 聚合而来。当前规则定义在 `core/scoring.py`。

### Follow

关系类型：`follows`

表示一个账号关注另一个账号。当前规则已定义，平台 adapter 是否写入取决于具体数据源。

### Mention

关系类型：`mentioned`

表示内容中提及另一个账号。当前规则已定义，平台 adapter 是否写入取决于具体数据源。

### Reply

关系类型：`replied_to`

表示一个账号回复另一个账号的评论。当前最小 adapter 可从评论父子关系派生。

### Comment

关系类型：`commented_on`

表示一个账号评论另一个账号发布的帖子、笔记或作品。当前最小 adapter 主要通过该关系构图。

### Repost

关系类型：`reposted`

表示一个账号转发另一个账号的内容。当前规则已定义，平台 adapter 是否写入取决于具体数据源。

## Weight

边权重表示关系强度，不是身份确认分数。

当前权重由 `core/edge_builder.py` 聚合，主要因素包括：

- 互动类型基础权重
- 回复高于普通评论的贡献
- 高评论数帖子下的互动降权，减少爆款内容噪声
- 多个不同帖子上的重复互动加权
- 最近互动的时间衰减
- 相同平台位置字段带来的小幅加权
- 证据数量与置信度聚合

输出字段：

- `edges.weight`
- `edges.confidence`
- `edges.interaction_count`
- `edges.evidence_count`
- `edges.first_seen`
- `edges.last_seen`

## Importance

节点重要性由图分析结果表示，不写入账号基础字段。

实现表：`node_scores`

当前指标：

- `degree_centrality`
- `betweenness_centrality`
- `pagerank`
- `community_id`
- `weighted_degree`

`weighted_degree` 是节点级指标，表示一个节点关联边权重的合计，不等同于单条边的 `weight`。

## Platform Metadata

平台 metadata 定义在 `adapters/registry.py`。

用途：

- 平台识别
- 平台别名
- URL markers
- adapter factory
- profile 输入归一化
- comment token 策略
- 图谱 UI 平台名称和 ID 标签

这些 metadata 不是业务数据，不进入图谱节点或边。`core/db.py` 目前仍在 `platforms` 表中种子写入基础平台清单；未来可改为轻量 metadata 驱动。

## 数据库存储结构

### 目前实现

核心表：

- `platforms`
- `accounts`
- `identities`
- `identity_accounts`
- `posts`
- `interactions`
- `edges`
- `evidences`
- `node_scores`
- `crawl_targets`
- `crawl_jobs`
- `crawl_history`
- `minimal_crawl_state`

默认路径：

```text
data/database/osge_overlay.db
```

### 未来规划

- 评论作为独立节点的可选模型
- 跨平台身份合并的人工确认流程
- 平台特有上下文 metadata 的通用表达
- 数据删除和清理记录
- 标准导入格式
- 可选图数据库后端
