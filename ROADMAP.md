# ROADMAP

## Phase 1: 基础数据模型

状态：进行中

- 建立 SQLite overlay 数据库
- 定义 `accounts`、`posts`、`interactions`、`edges`、`evidences`
- 建立 `identities` 与 `identity_accounts` 身份容器层
- 保留关系证据与来源记录
- 增加隐藏账号标记，避免默认硬删除

## Phase 2: 图谱构建

状态：进行中

- 从互动记录派生账号之间的有向边
- 聚合多次评论、回复、转发、提及或关注关系
- 保留边的证据数量、首次出现、最近出现和置信度
- 支持增量刷新时跳过已知评论和回复
- TODO：完善跨平台关系合并的人工确认流程

## Phase 3: 关系分析

状态：进行中

- 计算加权边
- 计算 degree centrality
- 计算 betweenness centrality
- 计算 PageRank
- 计算 weighted degree
- 计算社区编号
- TODO：补充评分解释导出和可复现实验记录

## Phase 4: 可视化系统

状态：进行中

- 本地 Web 图谱页面
- 节点详情面板
- 边证据查看
- 节点增量更新
- 账号隐藏与相邻孤立节点清理
- TODO：独立的身份容器管理视图
- TODO：导出可分享的脱敏图谱报告

## Phase 5: 多平台支持

状态：进行中

- Xiaohongshu 最小适配器已接入并完成本地 profile、post、comment 采集验证
- Douyin 最小适配器已接入并完成本地 profile、post、comment 采集验证
- 平台 registry 与通用 expansion runner 已作为新增平台入口
- Weibo 适配器占位
- Qzone 适配器占位
- TODO：接入第三个平台前评估 `adapters/platforms/{platform}/` 包结构
- TODO：平台字段白名单与合规检查

## Future

- 数据清理和删除请求流程
- 导入公开研究数据集的标准接口
- 可选图数据库后端
- 更完整的测试套件
- 更稳定的 API 文档
