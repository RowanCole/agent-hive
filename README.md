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
- [公共 API 使用文档](#公共-api-使用文档)
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
# 方式一：从 Git 安装（推荐，可直接导入使用）
pip install git+https://gitee.com/Rowancole/agent-hive.git

# 方式二：以包形式安装（本地开发）
pip install -e .

# 方式三：直接安装依赖
pip install -r requirements.txt
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

## 公共 API 使用文档

### 安装方式

```bash
pip install -e .     # 以包形式安装，之后可通过 import agent_hive 引入
```

### 导入入口

所有公开 API 统一通过 `agent_hive` 包导出：

```python
from agent_hive import MasterAgent, WorkerAgent, BaseAgent, BaseState
from agent_hive import AgentConfig
from agent_hive import tools_list, get_tools
```

### API 概览

| 类 / 函数 | 来源文件 | 用途 |
|-----------|---------|------|
| `AgentConfig` | [core/config.py](file:///c:/Users/sxl/Desktop/agent-hive/core/config.py) | 统一配置管理（LLM / 数据目录 / MCP） |
| `MasterAgent` | [core/master_agent.py](file:///c:/Users/sxl/Desktop/agent-hive/core/master_agent.py) | 根节点 Agent，负责任务拆分、子 Agent 管理、结果汇总 |
| `WorkerAgent` | [core/worker_agent.py](file:///c:/Users/sxl/Desktop/agent-hive/core/worker_agent.py) | 执行单元，可递归创建下层 Worker |
| `BaseAgent` | [core/base_agent.py](file:///c:/Users/sxl/Desktop/agent-hive/core/base_agent.py) | 抽象基类，实现自定义 Agent 时继承 |
| `BaseState` | [core/base_agent.py](file:///c:/Users/sxl/Desktop/agent-hive/core/base_agent.py) | LangGraph 状态定义，含 `task_plan` / `task_results` / `task_end` |
| `tools_list` | [core/tools.py](file:///c:/Users/sxl/Desktop/agent-hive/core/tools.py) | 内置工具列表（`write_file` + `read_file`） |
| `get_tools()` | [core/tools.py](file:///c:/Users/sxl/Desktop/agent-hive/core/tools.py) | 动态加载工具（含 MCP 远程工具） |
| `MemoryManager` | [core/memory.py](file:///c:/Users/sxl/Desktop/agent-hive/core/memory.py) | SQLite 持久化单例（通常通过 agent.memory 间接访问） |

---

#### `AgentConfig` — 统一配置

```python
from agent_hive import AgentConfig

config = AgentConfig(
    openai_api_key="sk-xxx",                 # Master LLM API Key
    openai_base_url="https://api.example.com/v1",
    llm_model="gpt-4",
    worker_agent_url="https://worker-api.com/v1",  # Worker 独立 LLM（可选）
    worker_agent_key="sk-worker-key",
    worker_llm_model="deepseek-chat",
    data_dir=".code-agent",                         # 数据目录（含 memory.db）
)

# 内置属性路径
config.data_path           # Path(".code-agent")
config.mcp_servers_path    # Path(".code-agent/mcp_servers.json")
config.memory_db_path      # Path(".code-agent/memory.db")
config.checkpoint_db_path  # Path(".code-agent/checkpoints.db")
```

支持通过 `.env` 文件自动加载同名环境变量（`OPENAI_API_KEY`、`OPENAI_BASE_URL` 等）。

---

#### `MasterAgent` — 主入口

```python
from agent_hive import MasterAgent, AgentConfig, tools_list

# 快速启动
agent = MasterAgent(tools=tools_list)
agent.chat()                           # 交互式对话

# 单次执行
messages = agent.run("创建一个 Python 斐波那契脚本")
print(messages[-1].content)            # 打印最终报告

# 指定 session_id 恢复上下文
messages = agent.run("继续之前的工作", thread_id="a1b2c3d4")

# 从 Checkpoint 断点续传
agent.resume(thread_id="a1b2c3d4")

# 自定义配置
config = AgentConfig(llm_model="gpt-4o")
agent = MasterAgent(tools=tools_list, config=config)
agent.chat()
```

**关键方法：**

| 方法 | 说明 |
|------|------|
| `run(task, thread_id="")` | 执行任务，返回消息列表（含最终报告） |
| `chat(message="")` | 交互式对话；传参执行单轮，不传进入循环 |
| `resume(thread_id="")` | 从 Checkpoint 断点恢复 |
| `create_sub_agent(name, system_prompt)` | 创建子 WorkerAgent（LLM 自主调用） |
| `publish_module_doc(title, content)` | 发布模块设计文档（跨 Agent 共享） |
| `query_module_docs(keyword)` | 查询其他 Agent 发布的模块文档 |
| `print_tree()` | 打印树形 Agent 结构 |
| `load_history_messages(limit=30)` | 加载历史消息对象 |
| `get_checkpoint_history(thread_id)` | 获取所有 Checkpoint 快照（时间旅行） |

---

#### `WorkerAgent` — 执行单元

```python
from agent_hive import WorkerAgent, BaseState, tools_list

worker = WorkerAgent(
    name="code-writer",
    tools=tools_list,
    system_prompt="你是一个代码编写助手",
    depth=1,
)
worker.run("编写一个冒泡排序的 Python 实现")

# 动态添加工具
worker.add_tool(custom_tool)
```

`WorkerAgent` 继承 `BaseAgent`，拥有与 `MasterAgent` 相同的方法集（`run`、`chat`、`create_sub_agent` 等），并额外提供：

| 方法 | 说明 |
|------|------|
| `add_tool(tool)` | 运行时动态添加工具并重新绑定 LLM |

---

#### `BaseAgent` — 自定义 Agent

```python
from agent_hive import BaseAgent, BaseState

class MyCustomAgent(BaseAgent):
    def __init__(self, tools, config=None):
        super().__init__(
            state=BaseState,
            tools=tools,
            system_prompt="你是一个自定义 Agent",
            agent_type="custom",
            depth=0,
        )
```

---

#### 工具系统

```python
from agent_hive import tools_list, get_tools

# 内置工具（write_file + read_file）
agent = MasterAgent(tools=tools_list)

# 动态加载 MCP 远程工具
all_tools = get_tools(mcp_servers_path=config.mcp_servers_path)
agent = MasterAgent(tools=all_tools)
```

| API | 返回 | 说明 |
|-----|------|------|
| `tools_list` | `list[tool]` | 内置工具：`write_file`、`read_file` |
| `get_tools(path)` | `list[tool]` | 内置工具 + 从 MCP 配置加载的远程工具 |

---

#### `MemoryManager` — 持久化层

通常通过 `agent.memory` 间接访问，不直接实例化。核心方法：

```python
# 会话管理
memory.create_session(agent_type="master")   # 创建会话，返回 session_id
memory.list_sessions(limit=20)               # 列出活跃会话
memory.archive_session(session_id)           # 归档会话

# 消息
memory.save_message(sid, "user", "你好")     # 存储消息
memory.load_messages(sid, limit=60)          # 读取历史消息

# 任务记录
memory.save_task(sid, plan, results, ends)   # 存储任务执行记录
memory.get_recent_tasks(limit=3)             # 读取最近任务

# 文件变更追踪
memory.record_file_change(sid, "a.py", "modify")
memory.get_modified_files(sid)

# 偏好
memory.set_preference("language", "zh-CN")
memory.get_preference("language", default="en")

# Worker 注册表
memory.register_worker(name="w1", session_id=sid, depth=1)
memory.get_worker("w1")
memory.get_all_workers()

# 模块文档
memory.publish_module_doc(agent_name="a1", ...)
memory.search_module_docs(keyword="API")
memory.get_all_module_docs_summary()
```

---

### 完整示例

```python
"""演示 Agent Hive 的完整使用流程"""
from agent_hive import MasterAgent, AgentConfig, tools_list

# 1. 配置
config = AgentConfig(llm_model="deepseek-chat")

# 2. 初始化 Agent
agent = MasterAgent(tools=tools_list, config=config)

# 3. 单次执行
messages = agent.run("创建一个 config.yaml 配置文件，包含数据库和日志设置")
print(messages[-1].content)

# 4. 交互模式
# agent.chat()

# 5. 查看 Agent 树形结构
agent.print_tree()

# 6. 发布模块文档（供其他 Agent 发现）
agent.publish_module_doc(
    title="配置模块接口",
    content="config.yaml 包含 database.host / database.port / logging.level 等字段",
    doc_type="interface",
)

# 7. 查询模块文档
docs = agent.query_module_docs(keyword="配置")
print(docs)
```

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
