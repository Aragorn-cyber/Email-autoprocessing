# 邮件 AI 助手 v1

本地运行的未读邮件整理工具。它通过普通 IMAP 只读获取时间窗内的未读邮件，结合确定性规则和 DeepSeek 进行来源分类、二级分类、重要性评分与摘要，并保存 SQLite 报告快照。

## v1 范围

- 多邮箱 `UNSEEN + SINCE N 天` 扫描，默认 7 天
- 同步 HTTP 请求，内部 `asyncio` 并发，上限 10
- 规则分 + AI 语义分，输出重要、一般、可丢弃三档
- 来源规则优先；未确认来源按发件域名稳定归一，AI 名称与明确的新分类提议写入待确认建议
- 可丢弃邮件在报告底部折叠，并显示归类原因摘要
- 跨账号重复邮件合并展示，保留所属账号
- 邮件详情页、当前/历史报告、账号管理、本地已读管理与基础查询 API
- 邮箱纯只读，不标记已读、不移动、不删除
- “本地已读”只控制后续报告是否隐藏邮件，可随时从管理页移除，不修改邮箱服务器状态

## 安装与启动

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

打开 `http://127.0.0.1:8000`。

## 配置

复制 `.env.example` 为 `.env`。LLM 默认配置：

```dotenv
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
LLM_API_KEY=
LLM_MAX_TOKENS=8192
LLM_BODY_CHAR_LIMIT=4000
LLM_RETRY_BACKOFF_SECONDS=1.0
```

- `LLM_MAX_TOKENS`：单次输出 token 上限，默认 8192。招聘汇总等长邮件需要更大的输出空间，模型若带推理过程，过小会导致“只思考不出结果”。
- `LLM_BODY_CHAR_LIMIT`：送入模型的邮件正文字符上限，默认 4000，超出部分截断（正文仍全文落库，只影响发给模型的 prompt）。
- `LLM_RETRY_BACKOFF_SECONDS`：重试前的等待秒数。AI 连续两次返回空内容时不再判失败，而是用规则兜底保留邮件并在报告中展示。

评分阈值、白名单/黑名单和各条规则权重也都能在 `.env` 中修改，完整字段见 `.env.example`。

新增邮箱账号时，数据库只保存授权码对应的环境变量名。例如填写 `EMAIL_MAIN_PASSWORD`，随后在 `.env` 增加：

```dotenv
EMAIL_MAIN_PASSWORD=你的邮箱授权码
```

不同邮箱应使用不同的环境变量名。账号的 IMAP 主机、端口、用户名、文件夹和扫描时间窗在网页中维护。

网易 163 邮箱使用 `imap.163.com:993`，文件夹填写 `INBOX`。接入层会在服务器支持时发送标准 IMAP `ID` 客户端声明，以满足网易的安全登录要求。

## API

- `POST /api/accounts`：新增邮箱账号
- `GET /api/accounts`：查询邮箱账号
- `PATCH /api/accounts/{id}`：更新、启用或停用账号
- `POST /api/scans`：同步执行扫描并返回报告 ID
- `GET /api/reports`：报告列表
- `GET /api/reports/latest`：最新报告
- `GET /api/reports/{id}`：报告快照和分类树
- `GET /api/mails/{id}`：邮件与评分详情
- `GET /api/read-mails`：分页查询本地已读名单
- `POST /api/read-mails/bulk`：批量加入本地已读名单（报告 A/B 区“一键已读”）
- `DELETE /api/read-mails`：清空本地已读名单（已读管理“一键移出”）
- `POST /api/read-mails/{id}`：加入本地已读名单，后续扫描报告不再展示
- `DELETE /api/read-mails/{id}`：移出本地已读名单
- `GET /api/important-mails`：分页查询本地重要邮件名单
- `POST /api/important-mails/{id}`：标记为重要邮件（仅本地记录，不改服务器）
- `DELETE /api/important-mails/{id}`：移除重要邮件标记

- `GET /api/categories`：二级分类
- `GET /api/suggestions`：只读待确认建议列表

接口交互文档位于 `http://127.0.0.1:8000/docs`。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

自动测试使用模拟 IMAP 和模拟 LLM，不读取真实邮箱，也不会消耗模型额度。

## 数据与安全

SQLite 默认写入 `data/email_ai_assistant.db`。`.env`、数据库、缓存和真实邮件样本均已加入 `.gitignore`。邮件正文以明文保存在本地数据库，不应将数据库上传、提交或公开。
