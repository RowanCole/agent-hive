# Agent Hive 架构文档

> 本文档深入描述 Agent Hive 框架的软件架构、核心设计理念、模块划分及关键实现细节。

---

## 目录

1. [整体架构概览](#1-整体架构概览)
2. [核心设计理念](#2-核心设计理念)
3. [模块详解](#3-模块详解)
   - [3.1 配置层 — AgentConfig](#31-配置层--agentconfig)
   - [3.2 持久化层 — MemoryManager](#32-持久化层--memorymanager)
   - [3.3 基础抽象层 — BaseAgent](#33-基础抽象层--baseagent)
   - [3.4 MasterAgent — 根节点](#34-masteragent--根节点)
   - [3.5 WorkerAgent — 执行单元](#35-workeragent--执行单元)
   - [3.6 工具系统](#36-工具系统)
   - [3.7 安全模块](#37-安全模块)
4. [数据流与执行流程](#4-数据流与执行流程)
5. [树形结构与深度控制](#5-树形结构与深度控制)
6. [持久化设计](#6-持久化设计)
7. [MCP 集成机制](#7-mcp-集成机制)
8. [扩展指南](#8-扩展指南)
9. [已知限制与注意事项](#9-已知限制与注意事项)

---

## 1. 整体架构概览

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Agent Hive                                │
│                                                                     │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐            │
│  │   agent_hive  │   │     core     │   │    utils     │            │
│  │  (公共 API)   │   │  (核心逻辑)   │   │  (工具模块)   │            │
│  │              │   │              │   │              │            │
│  │  __init__.py │   │  config.py   │   │  log.py      │            │
│  │  _cli.py     │──▶│  base_agent  │   │  security.py │            │
│  │  __main__.py │   │  master_agent│   └──────────────┘            │
│  └──────────────┘   │  worker_agent│                                │
│                     │  tools.py    │                                │
│                     │  memory.py   │                                │
│                     └──────┬───────┘                                │
│                            │                                        │
│               ┌────────────┴────────────┐                           │
│               ▼                         ▼                           │
│        ┌──────────┐             ┌──────────────┐                   │
│        │ SQLite   │             │  MCP Server   │                   │
│        │ memory.db│             │ (远程工具)    │                   │
│        │ checkpoints.db         └──────────────┘                   │
│        └──────────┘                                                │
└─────────────────────────────────────────────────────────────────────┘
```

### 分层说明

| 层级 | 目录 | 职责 |
|------|------|------|
| **API 层** | `agent_hive/` | 对外暴露的公共接口，CLI 入口 |
| **核心层** | `core/` | Agent 基类、状态机、工具系统、持久化、配置管理 |
| **工具层** | `utils/` | 日志、安全校验等横切关注点 |
| **数据层** | `.code-agent/` | SQLite 数据库、MCP 配置、项目上下文 |

---

## 2. 核心设计理念

### 2.1 分治（Divide and Conquer）

复杂任务 → MasterAgent 拆解 → 多个 WorkerAgent 分别执行 → 汇总结果。每个 Agent 只处理自己负责的子任务，避免单一 LLM 上下文过长和工具调用混乱。

### 2.2 树形分层

Agent 之间形成**多叉树**结构：
- MasterAgent 是根节点（depth=0）
- WorkerAgent 是中间节点或叶子节点（depth≥1）
- 树高上限为 `MAX_TREE_DEPTH=5`

每个节点可以创建子节点，子节点继承父节点的工具集和配置。

### 2.3 统一的状态图流水线

所有 Agent（无论 Master 还是 Worker）共享同一个 StateGraph 模板：

```
create_plan ──▶ exec_plan ──▶ call_llm ──▶ END
```

每个阶段都有明确的职责，LLM 在三个阶段中扮演不同角色：
- **create_plan**: LLM 作为"规划者"，将任务拆解为有序子任务
- **exec_plan**: LLM 作为"执行者"，逐个完成子任务（可调用工具）
- **call_llm**: LLM 作为"汇报者"，生成任务完成报告

### 2.4 共享基础设施

所有 Agent 共享：
- 同一 SQLite 实例（`MemoryManager` 单例）
- 同一 LangGraph Checkpoint 数据库
- 同一对象存储（`mcp_servers.json` 配置的远程工具）

### 2.5 可扩展性

- `BaseAgent` 是抽象基类，支持子类继承
- MasterAgent 和 WorkerAgent 的 LLM 可独立配置
- 工具系统支持运行时动态注入

---

## 3. 模块详解

### 3.1 配置层 — AgentConfig

**文件**: [core/config.py](file:///c:/Users/sxl/Desktop/agent-hive/core/config.py)

`AgentConfig` 继承自 `pydantic_settings.BaseSettings`，是框架的统一配置入口。

```
AgentConfig
├── MasterAgent LLM 配置
│   ├── openai_api_key     (环境变量: OPENAI_API_KEY)
│   ├── openai_base_url    (环境变量: OPENAI_BASE_URL)
│   └── llm_model          (环境变量: LLM_MODEL, 默认: gpt-4)
│
├── WorkerAgent LLM 配置（可选，带自动回退）
│   ├── worker_agent_url   (环境变量: WORKER_AGENT_URL)
│   ├── worker_agent_key   (环境变量: WORKER_AGENT_KEY)
│   └── worker_llm_model   (环境变量: WORKER_LLM_MODEL)
│
├── 数据路径
│   ├── data_dir           (默认: .code-agent)
│   ├── mcp_servers_file   (默认: mcp_servers.json)
│   ├── data_path          → Path(data_dir)
│   ├── mcp_servers_path   → data_path / mcp_servers_file
│   ├── memory_db_path     → data_path / memory.db
│   └── checkpoint_db_path → data_path / checkpoints.db
│
└── Worker 回退属性
    ├── worker_base_url    → worker_agent_url or openai_base_url
    ├── worker_api_key     → worker_agent_key or openai_api_key
    └── worker_model       → worker_llm_model or llm_model
```

**关键设计**:
- WorkerAgent 的 LLM 配置采用**回退模式**：如果没有单独配置 Worker 的 LLM，自动复用 MasterAgent 的配置。这允许用户在需要时让 Worker 使用不同的模型（例如更经济的模型）。
- 所有路径属性都是 `@property`，基于 `data_dir` 动态计算，保持一致性。

### 3.2 持久化层 — MemoryManager

**文件**: [core/memory.py](file:///c:/Users/sxl/Desktop/agent-hive/core/memory.py)

`MemoryManager` 是**线程安全的单例模式**实现，所有 Agent 共享同一个 SQLite 实例。

#### 数据库表结构

```
sessions          ── 会话表（id, agent_type, title, status, created_at, updated_at）
messages          ── 消息表（session_id, role, content, tool_calls, created_at）
task_records      ── 任务记录（session_id, task_plan, task_results, task_end, created_at）
file_changes      ── 文件变更追踪（session_id, file_path, operation, created_at）
preferences       ── 用户偏好（key, value）
workers           ── Worker 注册表（name, session_id, parent_id, depth, ...）
module_docs       ── 模块设计文档（agent_name, doc_type, title, content, version, ...）
```

#### 单例实现细节

```python
class MemoryManager:
    _instance: Optional["MemoryManager"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with _mem_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init(*args, **kwargs)
        return cls._instance
```

使用**双重检查锁**（Double-Checked Locking）确保线程安全，同时避免每次获取实例时的锁竞争。

#### 核心能力

| 能力 | 方法 | 用途 |
|------|------|------|
| 会话管理 | `create_session`, `list_sessions`, `archive_session` | 会话生命周期管理 |
| 消息持久化 | `save_message`, `load_messages` | 对话历史读写 |
| 任务记录 | `save_task`, `get_recent_tasks` | 任务执行结果持久化 |
| 文件追踪 | `record_file_change`, `get_modified_files` | 文件操作审计 |
| 偏好设置 | `set_preference`, `get_preference` | 用户配置持久化 |
| Worker 注册表 | `register_worker`, `get_worker`, `get_all_workers` | 树形结构元数据管理 |
| 模块文档 | `publish_module_doc`, `query_module_docs` | 跨 Agent 接口共享 |

### 3.3 基础抽象层 — BaseAgent

**文件**: [core/base_agent.py](file:///c:/Users/sxl/Desktop/agent-hive/core/base_agent.py)

`BaseAgent` 是整个框架的核心抽象类，封装了所有 Agent 共有的能力。

#### 类结构

```
BaseAgent
├── 属性
│   ├── config              AgentConfig 实例
│   ├── agent_type          "master" / "worker" / "base"
│   ├── tools               LangChain Tool 列表
│   ├── system_prompt       系统提示词
│   ├── depth               树深度（根节点为 0）
│   ├── parent_id           父 Agent 标识
│   ├── memory              MemoryManager 单例
│   ├── worker_dict         子 Agent 注册表（dict）
│   ├── session_id          当前会话 ID
│   ├── llm                 ChatOpenAI 实例
│   └── _graph              编译后的 StateGraph
│
├── 初始化流程
│   ├── 加载配置
│   ├── 创建/复用会话
│   ├── 加载历史记忆上下文
│   ├── 实例化 LLM（Master/Worker 可选不同模型）
│   ├── 注入子 Agent 管理工具
│   ├── 连接 Checkpoint 数据库
│   └── 编译 StateGraph
│
├── Graph 节点
│   ├── _create_plan()      阶段1: 制定计划
│   ├── _exec_plan()        阶段2: 执行计划
│   └── _call_llm()        阶段3: 生成报告
│
├── 树形管理
│   ├── create_sub_agent()  创建子 WorkerAgent
│   ├── get_sub_agent()     获取子 Agent
│   ├── list_sub_agents()   列出所有子 Agent
│   ├── print_tree()        打印子树结构
│   └── _check_depth()      检查深度限制
│
├── 持久化
│   ├── _save_message()     保存消息
│   ├── _save_task_result() 保存任务结果
│   ├── _record_file_op()   记录文件操作
│   ├── _load_memory_context()    加载历史上下文
│   └── load_history_messages()   加载历史消息对象
│
├── 模块文档
│   ├── publish_module_doc()     发布模块文档
│   └── query_module_docs()      查询模块文档
│
├── 公开接口
│   ├── run(task)           执行任务
│   ├── chat()              交互式对话
│   └── resume()            断点恢复
│
└── 检查点
    └── get_checkpoint_history()  时间旅行
```

#### StateGraph 节点详解

##### create_plan 节点

```
输入: 用户消息（HumanMessage）
流程:
  1. 构造规划 Prompt（含历史记忆上下文）
  2. LLM 将任务拆解为有序子任务列表
  3. 解析 "1. xxx\n2. xxx\n..." 格式输出
  4. 如果规划过程中 LLM 触发了工具调用，自动执行工具并继续规划
  5. 最多 10 轮 LLM 交互
输出: task_plan (list[str]), current_step=0, task_results=[], task_end=[]
```

**关键 Prompt 片段**:

```
你是一个任务规划专家。请将用户任务拆解为至少一个简单、可执行的子任务。
规则：
1. 只输出有序任务列表，不要任何多余解释
2. 每条任务以「数字+. 」开头
3. 一行一个任务
4. 必须生成至少 1 条任务
```

##### exec_plan 节点

```
输入: task_plan, current_step, task_results, task_end, messages
流程:
  1. 遍历 task_plan 中的每个子任务
  2. 对每个子任务:
     a. 构造执行 Prompt（含任务序号、内容、历史结果）
     b. LLM 循环执行（最多 20 轮迭代）
     c. 如果 LLM 调用工具 → 执行工具 → 继续
     d. 如果 LLM 返回文本且不含 "fail" → 标记成功
     e. 如果 LLM 返回 "fail" → 标记失败
  3. 持久化任务执行记录
输出: 更新后的 task_results, task_end, messages
```

##### call_llm 节点

```
输入: task_plan, task_results, task_end, messages
流程:
  1. 统计成功/失败数量
  2. 构造总结 Prompt（含原始任务、子任务列表、执行结果统计）
  3. LLM 生成格式化报告
  4. 持久化 assistant 消息
输出: 报告消息 → END
```

### 3.4 MasterAgent — 根节点

**文件**: [core/master_agent.py](file:///c:/Users/sxl/Desktop/agent-hive/core/master_agent.py)

`MasterAgent` 继承自 `BaseAgent`，是树形结构的根节点。

#### 与 BaseAgent 的区别

1. **默认 System Prompt**: 定义了 MasterAgent 的工作流程——使用 `create_sub_agent` 为每个模块创建子 Agent，给子 Agent 下达任务，汇总结果。
2. **Worker 恢复**: `_restore_workers()` 方法从 SQLite 读取持久化的 Worker 注册表，重建 `worker_dict`，实现跨会话的 Worker 状态恢复。
3. **状态类**: 使用 `MasterState`（当前与 `BaseState` 相同，但为未来扩展预留）。

#### Worker 恢复流程

```python
def _restore_workers(self):
    """从 SQLite 恢复所有 Worker 元数据，重建 worker_dict"""
    for row in self.memory.get_all_workers():
        if row["parent_id"] and row["parent_id"] != self._agent_name:
            continue  # 不是当前 master 直接创建的，跳过
        name = row["name"]
        worker = WorkerAgent(
            state=BaseState,
            name=name,
            tools=self.tools,
            system_prompt=row["system_prompt"] or "",
            session_id=row["session_id"],
            depth=row["depth"] or 1,
            parent_id=row["parent_id"] or "",
            config=self.config,
        )
        self.worker_dict[name] = {"worker": worker, ...}
```

### 3.5 WorkerAgent — 执行单元

**文件**: [core/worker_agent.py](file:///c:/Users/sxl/Desktop/agent-hive/core/worker_agent.py)

`WorkerAgent` 是 `BaseAgent` 的最简子类，目前仅添加了一个 `add_tool()` 方法用于运行时动态添加工具。

WorkerAgent 没有重写任何 Graph 节点，完全复用 `BaseAgent` 的 `create_plan → exec_plan → call_llm` 流水线。这意味着 WorkerAgent 接收到子任务后，其内部的 LLM 可以：

1. 将子任务进一步拆解（如果足够复杂）
2. 调用工具完成子任务
3. 生成子任务报告返回给父 Agent

这种设计使得**递归分解**成为可能：一个 Worker 如果发现子任务仍然太复杂，可以创建自己的子 Worker 继续拆解。

### 3.6 工具系统

**文件**: [core/tools.py](file:///c:/Users/sxl/Desktop/agent-hive/core/tools.py)

#### 工具分类

```
工具系统
├── 内置工具（始终可用）
│   ├── write_file(path, content)    写入文件（自动创建父目录）
│   ├── read_file(path)              读取文件内容
│   └── use_cmd(cmd)                 执行系统命令
│
├── MCP 工具（按需加载）
│   └── 通过 mcp_servers.json 配置文件动态加载
│
└── 管理工具（运行时注入）
    ├── create_sub_agent(name, system_prompt)    创建子 Agent
    ├── get_sub_agent(name)                      获取子 Agent
    └── list_sub_agents()                        列出所有子 Agent
```

#### MCP 工具加载机制

```python
async def _load_all_mcp_tools(mcp_servers_path: Path):
    mcp_config = _load_mcp_servers(mcp_servers_path)  # 读取 JSON
    all_tools = []
    for server_name, cfg in mcp_config.items():
        url = cfg.get("url", "").strip()
        if not url or cfg.get("type") != "streamable_http":
            continue
        tools = await load_mcp_tools(...)  # langchain-mcp-adapters
        all_tools.extend(tools)
    return all_tools
```

MCP 工具使用 `langchain-mcp-adapters` 库加载，支持 `streamable_http` 传输类型。启用工具名前缀（当有多个 MCP 服务器时）以避免工具名冲突。

#### 管理工具注入

管理工具的注入发生在 `BaseAgent.__init__` 中：

```python
def _inject_management_tools(self):
    # 1. 移除从父 Agent 继承的管理工具（func 指向父实例）
    self.tools = [t for t in self.tools
                  if t.name not in ("create_sub_agent", "get_sub_agent", "list_sub_agents")]

    # 2. 重新绑定到当前 self（深度不超过限制时）
    if self.depth < self.MAX_TREE_DEPTH:
        mgmt_tools = [
            StructuredTool.from_function(func=self.create_sub_agent, ...),
            StructuredTool.from_function(func=self.get_sub_agent, ...),
            StructuredTool.from_function(func=self.list_sub_agents, ...),
        ]
        self.tools = self.tools + mgmt_tools

    # 3. 重新绑定 LLM
    self.llm = self.llm.bind_tools(self.tools)
```

**为什么需要重新注入？** 子 Agent 从父 Agent 继承了 `self.tools` 列表，但其中的管理工具函数的 `self` 引用指向的是父 Agent 实例。重新注入确保当前 Agent 的管理工具正确绑定到自己的 `self`。

### 3.7 安全模块

**文件**: [utils/security.py](file:///c:/Users/sxl/Desktop/agent-hive/utils/security.py)

安全模块定义了两种校验机制，但目前**尚未集成**到工具调用流程中（即 `tools.py` 中的 `use_cmd` 直接执行命令，未调用 `validate_command`）。

#### 命令白名单

```python
safe_commands = {"dir", "cd", "type", "echo", "copy", "move", "del",
                 "mkdir", "rmdir", "python", "pip", "git", ...}

dangerous_commands = {"format", "shutdown", "restart", "taskkill",
                      "reg", "attrib", "cacls", "chkdsk", "sfc", ...}
```

#### 路径白名单

```python
allowed_dirs = {Path.cwd(), Path.cwd() / "output", Path.cwd() / "workspace"}
```

---

## 4. 数据流与执行流程

### 4.1 完整执行时序

```
用户输入
   │
   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  MasterAgent.run(task)                                              │
│                                                                     │
│  1. 加载历史记忆（最近 20 条消息 + 最近 3 个任务 + ...）            │
│  2. 构造初始 messages:                                              │
│     [SystemPrompt + 历史消息 + HumanMessage(task)]                  │
│  3. 调用 StateGraph                                                 │
│     │                                                               │
│     ├─ create_plan                                                  │
│     │   │  LLM 拆解任务 → ["子任务1", "子任务2", ...]               │
│     │   └─ 输出: task_plan, current_step=0                         │
│     │                                                               │
│     ├─ exec_plan                                                    │
│     │   │                                                           │
│     │   ├─ 子任务1                                                  │
│     │   │   ├─ LLM 决定 → 调用 create_sub_agent("worker-A")        │
│     │   │   │              └─ WorkerAgent.run(sub_task)             │
│     │   │   │                   ├─ create_plan (内部拆解)           │
│     │   │   │                   ├─ exec_plan (内部执行)             │
│     │   │   │                   └─ call_llm (内部报告)             │
│     │   │   └─ 记录结果: success/fail                               │
│     │   │                                                           │
│     │   ├─ 子任务2                                                  │
│     │   │   ├─ LLM 决定 → 调用 write_file / use_cmd 等工具         │
│     │   │   └─ 记录结果: success/fail                               │
│     │   │                                                           │
│     │   └─ ...                                                      │
│     │                                                               │
│     └─ call_llm                                                     │
│         │  LLM 生成任务完成报告                                      │
│         └─ 输出: 报告消息 → END                                     │
│                                                                     │
│  4. 返回 messages[-1] 给用户                                        │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 StateGraph 状态转换

```
State 结构:
{
    "task_plan": list[str],      # 子任务列表
    "current_step": int,         # 当前执行到的步骤
    "task_results": list[str],   # 每个子任务的结果
    "task_end": list[str],       # 每个子任务的结束状态 (success/fail/failed)
    "messages": list[BaseMessage]  # 完整的对话消息
}

状态转换:
create_plan → exec_plan → call_llm → __end__
      │            │           │
      │  update:   │  update:  │  update:
      │  task_plan │  task_end │  messages
      │  messages  │  results  │
```

### 4.3 工具调用循环（exec_plan 内部）

```
对每个子任务:
  for iter in range(20):
      LLM 响应
      ├─ 包含 tool_calls → 执行工具 → 继续循环
      └─ 文本回复
          ├─ 不含 "fail" → 标记 success → 进入下一个子任务
          └─ 含 "fail"    → 标记 fail   → 进入下一个子任务
  if 循环耗尽（20轮）→ 标记 failed
```

---

## 5. 树形结构与深度控制

### 5.1 树形结构示例

```
MasterAgent (depth=0, agent_type="master")
│
├─ WorkerAgent "data-collector" (depth=1)
│   │
│   ├─ WorkerAgent "web-scraper" (depth=2)
│   └─ WorkerAgent "api-fetcher" (depth=2)
│
└─ WorkerAgent "report-generator" (depth=1)
    │
    └─ WorkerAgent "chart-maker" (depth=2)
        │
        └─ WorkerAgent "data-viz" (depth=3)   ← 最大 5 层
```

### 5.2 深度控制机制

```python
MAX_TREE_DEPTH = 5

def _check_depth(self) -> bool:
    if self.depth >= self.MAX_TREE_DEPTH:
        return False
    return True

def _inject_management_tools(self):
    # 达到最大深度的 Agent 不会获得 create_sub_agent 等管理工具
    if self.depth < self.MAX_TREE_DEPTH:
        # 注入管理工具
        ...
```

当 Agent 的 `depth` 达到 `MAX_TREE_DEPTH` 时，`create_sub_agent`、`get_sub_agent`、`list_sub_agents` 三个管理工具不会注入到其 tools 列表中。这意味着 LLM 无法调用创建子 Agent 的工具，从而阻止了无限递归。

### 5.3 Worker 注册表持久化

每次创建子 Agent 时，`BaseAgent.create_sub_agent()` 会调用 `MemoryManager.register_worker()` 将 Worker 元数据写入 SQLite `workers` 表。这保证了：

1. **跨会话恢复**: MasterAgent 重启后可以通过 `_restore_workers()` 重建 `worker_dict`
2. **树形结构审计**: 可以通过 `get_all_workers()` 查询完整的树形结构

---

## 6. 持久化设计

### 6.1 双数据库架构

```
.code-agent/
├── memory.db          # MemoryManager 管理的应用数据
│   ├── sessions
│   ├── messages
│   ├── task_records
│   ├── file_changes
│   ├── preferences
│   ├── workers
│   └── module_docs
│
└── checkpoints.db     # LangGraph Checkpoint 管理的状态快照
    └── (由 SqliteSaver 自动管理)
```

### 6.2 记忆上下文注入

当 Agent 启动时，`_load_memory_context()` 从 SQLite 读取以下信息，注入到 `_create_plan` 节点的 Prompt 中：

1. **项目上下文**（`.code-agent/PROJECT.md`）
2. **模块设计文档摘要**（其他 Agent 发布的接口文档）
3. **最近 60 条对话历史**
4. **最近 3 个任务执行记录**
5. **用户偏好**（如语言设置）

这种设计让 Agent 在规划任务时能够感知到历史上下文和跨 Agent 的知识共享。

---

## 7. MCP 集成机制

### 7.1 配置加载流程

```
get_tools(mcp_servers_path)
  │
  ├─ mcp_servers_path 为 None
  │   └─ 返回 tools_list（仅内置工具）
  │
  └─ mcp_servers_path 有效
      ├─ _load_mcp_servers()
      │   └─ 读取 JSON → 解析 mcpServers 字典
      │
      └─ _load_all_mcp_tools()
          └─ 遍历每个服务器配置
              ├─ 验证 type="streamable_http" 且 url 非空
              ├─ load_mcp_tools() 通过 langchain-mcp-adapters 加载
              └─ 收集所有 MCP 工具
```

### 7.2 配置文件格式

```json
{
  "mcpServers": {
    "bing-search": {
      "type": "streamable_http",
      "url": "https://mcp.api-inference.modelscope.net/..."
    },
    "plot-server": {
      "type": "streamable_http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

### 7.3 内置 MCP 服务器

项目提供了一个基于 `mcp` 和 `matplotlib` 的几何绘图服务器：

- **文件**: [mcp-plot-server.py](file:///c:/Users/sxl/Desktop/agent-hive/mcp-plot-server.py)
- **支持的图形**: 点、线、圆、矩形、三角形、多边形、箭头
- **输出目录**: `plots/`

---

## 8. 扩展指南

### 8.1 自定义 Agent

继承 `BaseAgent` 并实现自定义逻辑：

```python
from agent_hive import BaseAgent, BaseState

class CustomAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(
            state=BaseState,
            agent_type="custom",
            **kwargs,
        )

    # 可选：重写 Graph 节点
    def _create_plan(self, state):
        # 自定义规划逻辑
        return super()._create_plan(state)
```

### 8.2 自定义 MCP 服务器

可以参考 `mcp-plot-server.py` 实现自定义 MCP 服务器，通过 `mcp_servers.json` 配置后即可被 Agent 调用。

### 8.3 添加新工具

```python
from langchain_core.tools import tool

@tool
def my_custom_tool(param: str) -> str:
    """工具描述"""
    return f"结果: {param}"

# 使用新工具
from agent_hive import MasterAgent, tools_list

custom_tools = tools_list + [my_custom_tool]
agent = MasterAgent(tools=custom_tools)
```

### 8.4 自定义状态

继承 `BaseState` 添加自定义字段：

```python
from agent_hive import BaseState

class CustomState(BaseState):
    custom_field: str = ""
    custom_list: list[str] = []
```

---

## 9. 已知限制与注意事项

### 9.1 当前限制

1. **安全模块未实际启用**: `utils/security.py` 定义了校验函数但未在 `tools.py` 中调用。`use_cmd` 工具直接执行命令，不经过安全校验。
2. **缺少自动化测试**: 项目无 `tests/` 目录，无 pytest 配置。
3. **Windows 特定**: `use_cmd` 在 Windows CMD 中执行命令，使用 `shell=True`。
4. **串行执行**: `exec_plan` 按顺序执行子任务，不支持并行。WorkerAgent 的 `run()` 也是同步调用的。

### 9.2 注意事项

- **LLM 成本**: 每次任务执行会多次调用 LLM（规划阶段最多 10 轮 + 每个子任务最多 20 轮 + 报告阶段 1 轮），对 API 有较大消耗。
- **上下文窗口**: 历史记忆注入会占用 LLM 上下文窗口，`load_history_messages` 默认加载 20 条。
- **SQLite 并发**: `check_same_thread=False` 允许跨线程访问，但在高并发场景下需注意写锁竞争。
- **Agent 名称**: `_agent_name` 格式为 `L{depth}-{agent_type}-{session_id[:4]}`，在日志中可唯一标识每个 Agent 实例。

---

*最后更新: 2025-06-20*
