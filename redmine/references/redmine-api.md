---
name: redmine
description: 当用户查询或者修改redmine任务时
---

# Redmine 工具技能

## 技能描述
通过Redmine REST API访问和操作Redmine问题跟踪系统，支持完整的CRUD操作（创建、读取、更新、删除）。

## 使用场景
- 查看问题详情、问题列表
- 创建、更新、删除问题
- 查看项目列表、项目详情
- 查看用户信息
- 添加/移除问题观察者
- 上传附件
- 按要求分析整理数据

## 配置信息

### Redmine地址
https://git.nationalchip.com/redmine

### API Key
见本技能目录下的 `SECRET.md`

### 认证方式
三种认证方式任选其一：
1. HTTP Header: `X-Redmine-API-Key: {API_KEY}` （推荐）
2. URL参数: `?key={API_KEY}`
3. HTTP Basic Auth: 用户名为API Key，密码随机

---

## API 资源列表

| 资源 | 状态 | 说明 |
|------|------|------|
| Issues | Stable | 问题管理 |
| Projects | Stable | 项目管理 |
| Users | Stable | 用户管理 |
| Time Entries | Stable | 工时记录 |
| Issue Statuses | Alpha | 问题状态列表 |
| Trackers | Alpha | 跟踪器列表 |
| Enumerations | Alpha | 优先级、活动类型 |
| Issue Categories | Alpha | 问题分类 |
| Versions | Alpha | 版本管理 |
| Wiki Pages | Alpha | Wiki页面 |
| Attachments | Beta | 附件管理 |
| Search | Alpha | 搜索功能 |
| My Account | Alpha | 当前账户信息 |

---

## Issues API

### 获取问题列表
```bash
curl -H "X-Redmine-API-Key: {API_KEY}" "{REDMINE_URL}/issues.json"
```

**常用过滤参数：**
| 参数 | 说明 | 示例 |
|------|------|------|
| `issue_id` | 指定问题ID | `issue_id=1,2,3` |
| `project_id` | 指定项目ID | `project_id=2` |
| `subproject_id` | 子项目ID | `subproject_id=!*` (不含子项目) |
| `tracker_id` | 跟踪器ID | `tracker_id=1` |
| `status_id` | 状态ID | `open`, `closed`, `*` (全部) |
| `assigned_to_id` | 分配给谁 | `me` 或用户ID |
| `parent_id` | 父问题ID | `parent_id=100` |
| `created_on` | 创建时间过滤 | `>=2024-01-01` |
| `updated_on` | 更新时间过滤 | `>=2024-01-01T08:00:00Z` |
| `cf_X` | 自定义字段X | `cf_1=abcdef` |

**分页参数：**
- `offset`: 偏移量（默认0）
- `limit`: 每页数量（默认25，最大100）
- `sort`: 排序字段，如 `updated_on:desc`

**关联数据（include参数）：**
- `attachments` - 附件
- `relations` - 关联问题

**示例：**
```bash
# 分配给我的未关闭问题
curl -H "X-Redmine-API-Key: {API_KEY}" \
  "{REDMINE_URL}/issues.json?assigned_to_id=me&status_id=open&limit=100"

# 指定项目的所有问题
curl -H "X-Redmine-API-Key: {API_KEY}" \
  "{REDMINE_URL}/issues.json?project_id=2&status_id=*&limit=100"

# 最近更新的问题
curl -H "X-Redmine-API-Key: {API_KEY}" \
  "{REDMINE_URL}/issues.json?sort=updated_on:desc&limit=20"
```

### 获取问题详情
```bash
curl -H "X-Redmine-API-Key: {API_KEY}" "{REDMINE_URL}/issues/{id}.json"
```

**include参数：**
- `children` - 子问题
- `attachments` - 附件
- `relations` - 关联问题
- `changesets` - 变更集
- `journals` - 历史记录
- `watchers` - 观察者
- `allowed_statuses` - 允许的状态

**示例：**
```bash
# 获取问题详情含历史记录
curl -H "X-Redmine-API-Key: {API_KEY}" \
  "{REDMINE_URL}/issues/434931.json?include=journals,attachments"
```

### 创建问题
```bash
curl -X POST -H "X-Redmine-API-Key: {API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "issue": {
      "project_id": 1,
      "subject": "问题标题",
      "priority_id": 4,
      "description": "问题描述"
    }
  }' \
  "{REDMINE_URL}/issues.json"
```

**问题属性：**
| 字段 | 说明 |
|------|------|
| `project_id` | 项目ID（必填） |
| `tracker_id` | 跟踪器ID |
| `status_id` | 状态ID |
| `priority_id` | 优先级ID |
| `subject` | 标题（必填） |
| `description` | 描述 |
| `category_id` | 分类ID |
| `fixed_version_id` | 目标版本ID |
| `assigned_to_id` | 分配给用户ID |
| `parent_issue_id` | 父问题ID |
| `watcher_user_ids` | 观察者ID数组 |
| `is_private` | 是否私有 |
| `estimated_hours` | 预估工时 |
| `custom_fields` | 自定义字段 |

### 更新问题
```bash
curl -X PUT -H "X-Redmine-API-Key: {API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "issue": {
      "status_id": 3,
      "notes": "更新备注说明"
    }
  }' \
  "{REDMINE_URL}/issues/{id}.json"
```

### 删除问题
```bash
curl -X DELETE -H "X-Redmine-API-Key: {API_KEY}" \
  "{REDMINE_URL}/issues/{id}.json"
```

### 添加观察者
```bash
curl -X POST -H "X-Redmine-API-Key: {API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"user_id": 123}' \
  "{REDMINE_URL}/issues/{id}/watchers.json"
```

### 移除观察者
```bash
curl -X DELETE -H "X-Redmine-API-Key: {API_KEY}" \
  "{REDMINE_URL}/issues/{id}/watchers/{user_id}.json"
```

### 获取问题关系
```bash
curl -H "X-Redmine-API-Key: {API_KEY}" \
  "{REDMINE_URL}/issues/{id}/relations.json"
```

也可以在问题详情里用 `include=relations` 一并取得。

### 创建问题关系
```bash
curl -X POST -H "X-Redmine-API-Key: {API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "relation": {
      "issue_to_id": 12346,
      "relation_type": "blocks"
    }
  }' \
  "{REDMINE_URL}/issues/12345/relations.json"
```

方向以 URL 中的问题为主语：上例表示 12345 阻塞 12346。`relation_type` 取值见下方“问题关系类型”。`precedes`/`follows` 额外接受 `delay`（天数），其他类型不接受。

创建后用 `GET /issues/{id}.json?include=relations` 复核关系确实建立，不要只凭 POST 返回码就声称边已连上。

### 删除问题关系
```bash
curl -X DELETE -H "X-Redmine-API-Key: {API_KEY}" \
  "{REDMINE_URL}/relations/{relation_id}.json"
```

删除用的是关系自身的 ID（来自关系列表的 `id` 字段），不是问题 ID。

---

## Projects API

### 获取项目列表
```bash
curl -H "X-Redmine-API-Key: {API_KEY}" "{REDMINE_URL}/projects.json"
```

**include参数：**
- `trackers` - 跟踪器
- `issue_categories` - 问题分类
- `enabled_modules` - 启用的模块
- `time_entry_activities` - 工时活动类型
- `issue_custom_fields` - 问题自定义字段

### 获取项目详情
```bash
curl -H "X-Redmine-API-Key: {API_KEY}" "{REDMINE_URL}/projects/{id}.json"
```

可以使用项目ID或项目标识符（identifier）。

### 创建项目（需要管理员权限）
```bash
curl -X POST -H "X-Redmine-API-Key: {API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "project": {
      "name": "项目名称",
      "identifier": "project_identifier",
      "description": "项目描述",
      "is_public": true
    }
  }' \
  "{REDMINE_URL}/projects.json"
```

### 归档/取消归档项目
```bash
# 归档
curl -X PUT -H "X-Redmine-API-Key: {API_KEY}" \
  "{REDMINE_URL}/projects/{id}/archive.xml"

# 取消归档
curl -X PUT -H "X-Redmine-API-Key: {API_KEY}" \
  "{REDMINE_URL}/projects/{id}/unarchive.xml"
```

---

## Time Entries API（工时记录）

### 获取工时记录列表
```bash
curl -H "X-Redmine-API-Key: {API_KEY}" "{REDMINE_URL}/time_entries.json"
```

**过滤参数：**
| 参数 | 说明 | 示例 |
|------|------|------|
| `user_id` | 用户ID | `me` 或用户ID |
| `project_id` | 项目ID | `project_id=2` |
| `issue_id` | 问题ID | `issue_id=12345` |
| `from` | 开始日期 | `from=2026-02-01` |
| `to` | 结束日期 | `to=2026-02-27` |
| `spent_on` | 花费日期 | `spent_on=2026-02-15` |
| `activity_id` | 活动类型ID | `activity_id=9` |

**分页参数：**
- `offset`: 偏移量（默认0）
- `limit`: 每页数量（默认25，最大100）

**示例：**
```bash
# 获取指定日期范围的工时记录
curl -H "X-Redmine-API-Key: {API_KEY}" \
  "{REDMINE_URL}/time_entries.json?from=2026-02-01&to=2026-02-27&limit=100"

# 获取指定项目的工时
curl -H "X-Redmine-API-Key: {API_KEY}" \
  "{REDMINE_URL}/time_entries.json?project_id=2&limit=100"

# 获取我的工时记录
curl -H "X-Redmine-API-Key: {API_KEY}" \
  "{REDMINE_URL}/time_entries.json?user_id=me"
```

### 创建工时记录
```bash
curl -X POST -H "X-Redmine-API-Key: {API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "time_entry": {
      "issue_id": 12345,
      "spent_on": "2026-02-15",
      "hours": 2.5,
      "activity_id": 9,
      "comments": "开发工作"
    }
  }' \
  "{REDMINE_URL}/time_entries.json"
```

### 更新工时记录
```bash
curl -X PUT -H "X-Redmine-API-Key: {API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "time_entry": {
      "hours": 3.0,
      "comments": "更新后的备注"
    }
  }' \
  "{REDMINE_URL}/time_entries/{id}.json"
```

### 删除工时记录
```bash
curl -X DELETE -H "X-Redmine-API-Key: {API_KEY}" \
  "{REDMINE_URL}/time_entries/{id}.json"
```

**工时记录属性：**
| 字段 | 说明 |
|------|------|
| `issue_id` | 问题ID（与project_id二选一） |
| `project_id` | 项目ID（与issue_id二选一） |
| `spent_on` | 花费日期 |
| `hours` | 工时数 |
| `activity_id` | 活动类型ID |
| `comments` | 备注 |

---

## Users API

### 获取当前用户信息
```bash
curl -H "X-Redmine-API-Key: {API_KEY}" "{REDMINE_URL}/users/current.json"
```

**include参数：**
- `memberships` - 项目成员关系
- `groups` - 所属组

### 获取用户详情
```bash
curl -H "X-Redmine-API-Key: {API_KEY}" \
  "{REDMINE_URL}/users/{id}.json?include=memberships,groups"
```

### 获取用户列表（需要管理员权限）
```bash
curl -H "X-Redmine-API-Key: {API_KEY}" "{REDMINE_URL}/users.json"
```

**过滤参数：**
- `status`: 用户状态（1=活跃，2=注册，3=锁定）
- `name`: 按登录名/姓名/邮箱过滤
- `group_id`: 按组过滤

---

## Attachments API

### 上传附件
```bash
# 第一步：上传文件获取token
curl -X POST -H "X-Redmine-API-Key: {API_KEY}" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @file.png \
  "{REDMINE_URL}/uploads.json?filename=file.png"

# 返回：{"upload":{"token":"7167.ed1ccdb093229ca1bd0b043618d88743"}}

# 第二步：创建/更新问题时关联附件
curl -X POST -H "X-Redmine-API-Key: {API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "issue": {
      "project_id": 1,
      "subject": "带附件的问题",
      "uploads": [
        {"token": "7167.ed1ccdb093229ca1bd0b043618d88743", "filename": "file.png", "content_type": "image/png"}
      ]
    }
  }' \
  "{REDMINE_URL}/issues.json"
```

---

## 其他常用API

### 获取问题状态列表
```bash
curl -H "X-Redmine-API-Key: {API_KEY}" "{REDMINE_URL}/issue_statuses.json"
```

### 获取跟踪器列表
```bash
curl -H "X-Redmine-API-Key: {API_KEY}" "{REDMINE_URL}/trackers.json"
```

### 获取优先级列表
```bash
curl -H "X-Redmine-API-Key: {API_KEY}" "{REDMINE_URL}/enumerations/issue_priorities.json"
```

### 搜索
```bash
curl -H "X-Redmine-API-Key: {API_KEY}" \
  "{REDMINE_URL}/search.json?q=关键词"
```

---

## 自定义字段操作

### 读取自定义字段
```json
{
  "issue": {
    "custom_fields": [
      {"value": "1.0.1", "name": "Affected version", "id": 1},
      {"value": "Fixed", "name": "Resolution", "id": 2}
    ]
  }
}
```

### 更新自定义字段
```bash
curl -X PUT -H "X-Redmine-API-Key: {API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "issue": {
      "custom_fields": [
        {"id": 1, "value": "新值"}
      ]
    }
  }' \
  "{REDMINE_URL}/issues/{id}.json"
```

---

## 状态ID对照表

| ID | 状态名称 |
|----|----------|
| 1 | 新建(New) |
| 2 | 进行中(In Progress) |
| 3 | 已解决(Resolved) |
| 4 | 反馈(Feedback) |
| 5 | 已关闭(Closed) |
| 6 | 已拒绝(Rejected) |

---

## 执行流程

当用户请求Redmine操作时：

1. **理解意图**：分析用户要做什么（查看/查询/创建/更新/删除/分析）
2. **构造请求**：根据意图构造API请求，选择合适的端点和参数
3. **执行请求**：调用API获取/更新数据
4. **处理分页**：如数据量大，需要多次请求获取完整数据
5. **分析整理**：按要求分析数据并整理输出
6. **返回结果**：以清晰格式呈现给用户

---

## 示例用法

| 用户请求 | API操作 |
|----------|---------|
| "查看Redmine #434931" | `GET /issues/434931.json` |
| "查看分配给我的问题" | `GET /issues.json?assigned_to_id=me` |
| "查看项目X的所有问题" | `GET /issues.json?project_id=X&status_id=*` |
| "更新#12345状态为已解决" | `PUT /issues/12345.json` |
| "给#12345添加备注" | `PUT /issues/12345.json` (notes字段) |
| "创建一个新问题" | `POST /issues.json` |
| "查看我的项目列表" | `GET /projects.json` |
| "搜索包含XX的问题" | `GET /search.json?q=XX` |

---

## 注意事项

1. **API Key安全**：API Key请妥善保管，不要泄露
2. **分页限制**：默认返回25条，最大100条，大量数据需分页请求
3. **Content-Type**：POST/PUT请求必须设置 `Content-Type: application/json`
4. **权限控制**：部分操作需要管理员权限
5. **书签功能**：标准API不支持书签，书签可能是插件功能，需通过浏览器访问

---

---

## Redmine核心概念

### 问题关系类型
| 关系类型 | 说明 |
|----------|------|
| related to | 相关问题，仅添加链接 |
| duplicates | 重复问题，关闭A会自动关闭B |
| duplicated by | 被重复，B重复A的逆关系 |
| blocks | 阻塞，B阻塞A时A无法关闭 |
| blocked by | 被阻塞，blocks的逆关系 |
| precedes | 前置，A需在B开始前X天完成 |
| follows | 后续，precedes的逆关系 |
| copied from | 复制来源 |
| copied to | 复制到 |

### 子任务(Subtask)
- 子任务可以属于不同的项目（需管理员配置）
- 父任务属性自动计算：
  - 完成百分比 = 子任务的加权平均
  - 开始日期 = 子任务最早日期
  - 截止日期 = 子任务最晚日期
  - 耗时 = 子任务耗时总和
  - 预估工时 = 子任务预估总和
  - 优先级 = 子任务最高优先级

### 跟踪器(Tracker)
默认跟踪器类型：
- Bug - 缺陷
- Feature - 功能
- Support - 支持

### 自定义查询(Custom Query)
用户可以保存常用的过滤器组合为自定义查询：
- 公开查询：所有人可见
- 私有查询：仅创建者可见
- 可自定义显示列

### My Page区块
用户个性化页面可显示的区块：
- Issues assigned to me - 分配给我的问题
- Reported issues - 我报告的问题
- Watched issues - 我关注的问题
- Calendar - 日历
- Documents - 文档
- Latest news - 最新新闻
- Spent time - 耗时记录

---

## 书签功能（插件扩展）

书签是公司Redmine安装的插件功能，非标准API。

### 书签API端点
```
# 添加书签
POST /projects/:project_identifier/bookmark

# 移除书签
DELETE /projects/:project_identifier/bookmark
```

**注意**：
- 需要CSRF token（authenticity_token）
- 建议通过浏览器自动化操作

### 获取书签列表
标准API和插件API均未提供全局书签列表端点。可选方案：
1. 浏览器自动化访问项目页面检查书签状态
2. 数据库直接查询书签插件表

网页访问地址：https://git.nationalchip.com/redmine

---

## 参考资料

- [Redmine官方文档](https://www.redmine.org/guide)
- [REST API文档](https://www.redmine.org/projects/redmine/wiki/Rest_api)
- [Issues API](https://www.redmine.org/projects/redmine/wiki/Rest_Issues)
- [Projects API](https://www.redmine.org/projects/redmine/wiki/Rest_Projects)
- [Users API](https://www.redmine.org/projects/redmine/wiki/Rest_Users)