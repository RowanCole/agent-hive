<div align="center">
  <h1>🐝 Agent Hive</h1>
  <p><strong>基于 LangGraph + MCP 的多 Agent 分层协作框架</strong></p>
  <p>MasterAgent 将复杂任务自动拆解为多级子任务，分发到树形结构的 WorkerAgent 集群（Hive）分层协同执行，最终汇总结果并生成验收报告。</p>
  <p>
    <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License">
    <img src="https://img.shields.io/badge/status-alpha-yellow.svg" alt="Alpha">
  </p>
</div>

---

## 目录

- [为什么选择 Agent Hive？](#为什么选择-agent-hive)
- [快速开始](#快速开始)
- [使用示例](#使用示例)
- [核心特性](#核心特性)
- [项目结构](#项目结构)
- [配置](#配置)
- [作为框架使用](#作为框架使用)
- [MCP 服务器](#mcp-服务器)
- [依赖](#依赖)
- [路线图](#路线图)
- [许可证](#许可证)

---

## 为什么选择 Agent Hive？

传统单 Agent 方案在处理复杂任务时，LLM 容易陷入上下文过长、工具调用混乱、单一模型能力不足等问题。

**Agent Hive** 采用**分治思想**：

1. 收到复杂任务 → MasterAgent 拆解为有序子任务
2. 每个子任务 → 由独立的 WorkerAgent 执行（可递归创建下层 Worker）
3. 所有 Worker 汇总 → MasterAgent 生成验收报告

这种**树形分层架构**让每个 Agent 只关注自己负责的子任务，大幅提升复杂任务的成功率和可追溯性。

---

## 快速开始

### 前置要求

- Python 3.10+
- 一个 OpenAI 兼容的 API Key

### 安装

```bash
# 方式一：直接安装依赖
pip install -r requirements.txt

# 方式二：以包形式安装（推荐，可导入使用）
pip install -e .
```

### 配置

在项目根目录创建 `.env` 文件：

```env
# 必填：LLM 配置（兼容 OpenAI / DeepSeek / 任意 OpenAI 兼容 API）
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat

# 可选：WorkerAgent 独立 LLM（不设则复用 Master 配置）
WORKER_AGENT_URL=https://worker-api-endpoint/v1
WORKER_AGENT_KEY=your_worker_key_here
WORKER_LLM_MODEL=worker-model-name
```

### 运行

```bash
# 交互模式
agent-hive

# 或
python -m agent_hive

# 或
python main.py
```

进入交互式对话后，直接输入任务即可：

```
> 搜索最近 AI 行业新闻，整理成报告保存到 report.txt
```

---

## 使用示例

### 基础用法

```python
from agent_hive import MasterAgent, tools_list

agent = MasterAgent(tools=tools_list)
agent.chat()  # 进入交互模式
```

### 自定义配置

```python
from agent_hive import MasterAgent, AgentConfig

config = AgentConfig(
    openai_api_key="sk-xxx",
    openai_base_url="https://api.example.com/v1",
    llm_model="gpt-4",
    # WorkerAgent 可独立配置 LLM
    worker_agent_url="https://worker-api.example.com/v1",
    worker_agent_key="sk-worker-key",
    worker_llm_model="deepseek-chat",
    # 自定义数据目录
    data_dir="/path/to/data",
)

agent = MasterAgent(tools_list, config=config)
agent.chat()
```

### 单次执行

```python
agent = MasterAgent(tools=tools_list)
messages = agent.run("创建一个 Python 脚本，实现斐波那契数列")
print(messages[-1].content)
```

### 恢复执行（断点续传）

```python
# 执行中断后，使用同一 session_id 恢复
agent.resume(thread_id="your-session-id")
```

---

## 核心特性

### 🧠 多 Agent 树形协作

- **MasterAgent**（根节点）：接收用户任务，LLM 自主拆解为有序子任务，创建 WorkerAgent 执行，最终汇总生成报告
- **WorkerAgent**（工作节点）：执行具体子任务，可继续创建下层 WorkerAgent（最多 **5 层**树深度）
- 所有 Agent 共享同一套基础设施：工具集、持久化记忆、检查点

### 🔧 工具系统

| 类型 | 工具 | 说明 |
|------|------|------|
| 内置工具 | `write_file` / `read_file` | 文件读写（自动创建父目录） |
| 内置工具 | `use_cmd` | 执行系统命令（1 小时超时，安全策略限制） |
| MCP 工具 | 动态加载 | 通过 MCP 协议接入任意远程工具服务 |
| 管理工具 | `create_sub_agent` / `get_sub_agent` / `list_sub_agents` | 运行时注入的子 Agent 管理 |

### 🔗 MCP 协议集成

通过 [MCP (Model Context Protocol)](https://modelcontextprotocol.io) 动态加载远程工具服务，支持任意数量的 MCP 服务端。

```json
{
  "mcpServers": {
    "bing-search": {
      "type": "streamable_http",
      "url": "https://your-mcp-server.com/mcp"
    }
  }
}
```

项目内置了一个**几何绘图 MCP 服务器**（`mcp-plot-server.py`），支持绘制点、线、圆、矩形、三角形、多边形、箭头等图形。

### 💾 持久化记忆系统

基于 SQLite 实现全量持久化，所有 Agent 共享同一实例：

- 会话管理（创建、归档、恢复）
- 对话历史持久化（自动注入上下文）
- 任务执行记录（含成功/失败统计）
- 文件变更追踪
- 用户偏好设置
- Worker 注册表（树形结构元数据）
- 模块设计文档（跨 Agent 接口共享）

### 📌 断点续传（Checkpoint）

基于 LangGraph Checkpoint SQLite 实现：

- 支持 `resume()` 从中断点恢复执行
- 支持时间旅行（`get_state_history()`）查看所有状态快照

### 🔒 安全控制

- 命令执行白名单
- 危险命令拦截（如 `format`、`shutdown`、`reg` 等）
- 文件访问路径白名单

---

## 项目结构

```
agent-hive/
├── pyproject.toml                 # 包构建配置
├── main.py                       # 入口文件
├── requirements.txt              # 依赖清单
├── .env                          # 环境变量配置
│
├── agent_hive/                   # 公共 API 包
│   ├── __init__.py               # 框架入口：from agent_hive import ...
│   ├── __main__.py               # python -m agent_hive
│   └── _cli.py                   # CLI 入口逻辑
│
├── core/                         # 核心逻辑
│   ├── config.py                 # AgentConfig 统一配置（Pydantic Settings）
│   ├── base_agent.py             # Agent 抽象基类（状态机、树形管理、持久化）
│   ├── master_agent.py           # MasterAgent 实现（根节点）
│   ├── worker_agent.py           # WorkerAgent 实现（执行单元）
│   ├── tools.py                  # 内置工具 + MCP 工具加载
│   └── memory.py                 # SQLite 持久化层（单例模式）
│
├── utils/                        # 工具模块
│   ├── log.py                    # 日志配置
│   └── security.py               # 安全校验（命令/路径白名单）
│
├── mcp-plot-server.py            # MCP 几何绘图服务器
│
├── .code-agent/                  # 运行数据目录
│   ├── mcp_servers.json          # MCP 服务器配置
│   ├── memory.db                 # SQLite 持久化数据库
│   └── checkpoints.db            # LangGraph Checkpoint 数据库
│
└── plots/                        # 几何绘图输出目录
```

---

## 配置

全部配置通过 `core/config.py` 的 `AgentConfig` 类管理（继承 `pydantic_settings.BaseSettings`），支持环境变量 / `.env` 文件 / 直接传参。

| 环境变量 | 对应属性 | 默认值 | 说明 |
|---------|---------|--------|------|
| `OPENAI_API_KEY` | `openai_api_key` | `""` | MasterAgent LLM API Key |
| `OPENAI_BASE_URL` | `openai_base_url` | `""` | MasterAgent LLM API 地址 |
| `LLM_MODEL` | `llm_model` | `gpt-4` | MasterAgent 模型名 |
| `WORKER_AGENT_URL` | `worker_agent_url` | `""` | WorkerAgent 独立 API 地址 |
| `WORKER_AGENT_KEY` | `worker_agent_key` | `""` | WorkerAgent 独立 API Key |
| `WORKER_LLM_MODEL` | `worker_llm_model` | `""` | WorkerAgent 独立模型名 |

> WorkerAgent 不单独配置时，自动回退使用 MasterAgent 的配置。

---

## MCP 服务器

项目内置了两个 MCP 服务器示例：

```bash
# 几何绘图服务器（基于 matplotlib）
python mcp-plot-server.py

# 数学运算服务器
python mcp_math_server.py
```

在 `.code-agent/mcp_servers.json` 中配置后，Agent Hive 启动时将自动加载这些 MCP 工具。

---

## 依赖

主要依赖（完整清单见 `requirements.txt`）：

| 包 | 用途 |
|----|------|
| `langchain` / `langchain-core` | LLM 应用框架 |
| `langchain-openai` | OpenAI 兼容 API 适配器 |
| `langchain-mcp-adapters` | MCP 工具加载 |
| `langgraph` / `langgraph-checkpoint-sqlite` | 状态图引擎 + 断点续传 |
| `mcp` | Model Context Protocol SDK |
| `pydantic` / `pydantic-settings` | 数据模型与配置管理 |
| `python-dotenv` | `.env` 文件加载 |
| `matplotlib` | 几何绘图 MCP 服务 |

---

## 路线图

- [ ] 完善安全模块集成（命令/路径校验接入工具调用流程）
- [ ] 单元测试与集成测试
- [ ] 支持更多 Agent 拓扑结构（DAG、并行广播等）
- [ ] Web UI 管理面板
- [ ] 更多内置 MCP 服务器模板
- [ ] 与 LangSmith 集成（可观测性）

---

## 许可证

[MIT License](LICENSE)

---

## 致谢

- [LangGraph](https://github.com/langchain-ai/langgraph) — Agent 状态图引擎
- [MCP](https://modelcontextprotocol.io) — Model Context Protocol
- [LangChain](https://github.com/langchain-ai/langchain) — LLM 应用框架
