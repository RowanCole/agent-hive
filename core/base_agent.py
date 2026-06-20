"""Agent 抽象基类 — 状态图（create_plan → exec_plan → call_llm）+ SQLite 持久化 + 树形管理。"""
import asyncio
import sqlite3
import time
from datetime import datetime
from enum import Enum
from typing import Annotated, Optional, TypedDict, Literal
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import MessagesState, StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command
from langgraph.checkpoint.sqlite import SqliteSaver

from utils.log import getLogger
from core.config import AgentConfig
from core.memory import MemoryManager

logger = getLogger("base-agent")


class TaskState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"
    PAUSED = "paused"


class BaseState(MessagesState):
    task_plan: list[str]
    current_step: int
    task_results: list[str]
    task_end: list[str]


class BaseAgent:
    """抽象基类 — 树形结构 Agent，最大深度 5 层。"""

    MAX_TREE_DEPTH = 5

    def __init__(self, state: type[BaseState] = BaseState, tools: list = [],
                 system_prompt: str = "", agent_type: str = "base",
                 session_id: str = "", depth: int = 0, parent_id: str = "",
                 config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
        self.agent_type = agent_type
        self.tools = tools
        self.system_prompt = system_prompt
        self.depth = depth
        self.parent_id = parent_id
        self.memory = MemoryManager()
        self.worker_dict: dict = {}
        self.session_id = session_id or self.memory.create_session(agent_type=agent_type)

        indent = "  " * self.depth
        logger.info(f"{indent}[L{self.depth} {self.agent_type}] 会话 {self.session_id} 已激活"
                    + (f" (父={self.parent_id})" if self.parent_id else ""))

        self._history_context = self._load_memory_context()
        self._agent_name = f"L{self.depth}-{self.agent_type}-{self.session_id[:4]}"

        if agent_type == "worker":
            self.model = self.config.worker_model
            self.llm = ChatOpenAI(base_url=self.config.worker_base_url,
                                   api_key=self.config.worker_api_key, model=self.model)
        else:
            self.model = self.config.llm_model
            self.llm = ChatOpenAI(base_url=self.config.openai_base_url,
                                   api_key=self.config.openai_api_key, model=self.model)

        self._inject_management_tools()

        self._checkpoint_conn = sqlite3.connect(
            str(self.config.checkpoint_db_path), check_same_thread=False)
        self._checkpointer = SqliteSaver(self._checkpoint_conn)
        self._graph = self._build().compile(checkpointer=self._checkpointer)
        logger.debug(f"[{self.agent_type}] Graph 编译成功")

    def _inject_management_tools(self):
        """重新绑定子 Agent 管理工具到当前实例（替换从父 Agent 继承的引用）。"""
        from langchain_core.tools import StructuredTool

        self.tools = [t for t in self.tools
                      if t.name not in ("create_sub_agent", "get_sub_agent", "list_sub_agents")]

        if self.depth < self.MAX_TREE_DEPTH:
            mgmt_tools = [
                StructuredTool.from_function(func=self.create_sub_agent, name="create_sub_agent",
                    description="创建一个子 Agent 负责执行子任务。树高上限为 5 层"),
                StructuredTool.from_function(func=self.get_sub_agent, name="get_sub_agent",
                    description="获取指定名称的子 Agent"),
                StructuredTool.from_function(func=self.list_sub_agents, name="list_sub_agents",
                    description="列出当前 Agent 的所有子 Agent"),
            ]
            self.tools = self.tools + mgmt_tools
        self.llm = self.llm.bind_tools(self.tools)

    def _load_memory_context(self) -> str:
        parts = []
        project = self.memory.load_project_context()
        if project:
            parts.append(f"[项目上下文]\n{project}")
        module_summary = self.memory.get_all_module_docs_summary()
        if module_summary:
            parts.append(module_summary)
        history = self.memory.load_messages(self.session_id, limit=60)
        if history:
            lines = ["[历史对话（最近60条）]"]
            for r in history:
                lines.append(f"{r['role']}: {r['content'][:300]}")
            parts.append("\n".join(lines))
        tasks = self.memory.get_recent_tasks(limit=3)
        if tasks:
            lines = ["[最近完成的任务]"]
            for plan, results, ends in tasks:
                lines.append(f"  Plan: {plan[:3]}... → {sum(1 for e in ends if e == 'success')}/{len(ends)} 成功")
            parts.append("\n".join(lines))
        lang = self.memory.get_preference("language")
        if lang:
            parts.append(f"[用户偏好] 使用语言: {lang}")
        return "\n\n".join(parts)

    def _save_message(self, role: str, content: str, tool_calls=None):
        self.memory.save_message(self.session_id, role, content, tool_calls)
        self.memory.touch_session(self.session_id)

    def _save_task_result(self, task_plan: list, task_results: list, task_end: list):
        self.memory.save_task(self.session_id, task_plan, task_results, task_end)

    def _record_file_op(self, file_path: str, operation: str):
        self.memory.record_file_change(self.session_id, file_path, operation)

    def publish_module_doc(self, title: str, content: str, doc_type: str = "interface") -> int:
        """发布模块设计文档，供其他 Agent 查询。"""
        doc_id = self.memory.publish_module_doc(
            agent_name=self._agent_name, agent_type=self.agent_type,
            session_id=self.session_id, title=title, content=content, doc_type=doc_type)
        logger.info(f"[{self._agent_name}] 发布模块文档 #{doc_id}: {title}")
        return doc_id

    def query_module_docs(self, keyword: str = "", agent_type: str = None) -> list:
        """查询其他 Agent 发布的模块文档。"""
        if keyword:
            return self.memory.search_module_docs(keyword)
        return self.memory.list_module_docs(agent_type=agent_type)

    def _check_depth(self) -> bool:
        if self.depth >= self.MAX_TREE_DEPTH:
            logger.warning(f"[{self._agent_name}] 已达最大深度 {self.MAX_TREE_DEPTH}，无法创建子 Agent")
            return False
        return True

    def create_sub_agent(self, name: str, system_prompt: str = ""):
        """创建子 WorkerAgent，继承父 Agent 的工具集与配置。"""
        if not self._check_depth():
            return None
        from core.worker_agent import WorkerAgent
        child_depth = self.depth + 1
        child_session = self.memory.create_session(agent_type="worker")
        sub = WorkerAgent(state=BaseState, name=name, tools=self.tools,
                          system_prompt=system_prompt, session_id=child_session,
                          depth=child_depth, parent_id=self._agent_name, config=self.config)
        self.worker_dict[name] = {
            "worker": sub, "system_prompt": system_prompt, "tools": self.tools,
            "tasks": "当前 worker 没有任务", "depth": child_depth, "parent": self._agent_name,
        }
        self.memory.register_worker(name=name, session_id=child_session,
            system_prompt=system_prompt, tools=[t.name for t in (self.tools or [])],
            task_summary="当前 worker 没有任务", depth=child_depth, parent_id=self._agent_name)
        logger.info(f"{'  ' * child_depth}[L{child_depth} worker] {name} 已创建 "
                    f"(父={self._agent_name}, session={child_session})")
        return sub

    def get_sub_agent(self, name: str):
        return self.worker_dict.get(name)

    def list_sub_agents(self):
        return [{"name": k, "depth": v["depth"], "parent": v["parent"], "tasks": v["tasks"]}
                for k, v in self.worker_dict.items()]

    def print_tree(self, indent: int = 0):
        prefix = "  " * indent
        print(f"{prefix}└─ [{self._agent_name}] ({len(self.worker_dict)} 个子Agent)")
        for name, info in self.worker_dict.items():
            w = info["worker"]
            if hasattr(w, "print_tree"):
                w.print_tree(indent + 1)
            else:
                print(f"{prefix}    └─ {name}")

    def load_history_messages(self, limit=30):
        from langchain_core.messages import HumanMessage as HM, AIMessage as AIM, ToolMessage as TM
        rows = self.memory.load_messages(self.session_id, limit=limit)
        msgs = []
        for r in rows:
            if r["role"] == "user":
                msgs.append(HM(content=r["content"]))
            elif r["role"] == "assistant":
                msgs.append(AIM(content=r["content"]))
            elif r["role"] == "tool":
                msgs.append(TM(content=r["content"], tool_call_id=""))
        return msgs

    def _build(self):
        builder = StateGraph(BaseState)
        builder.add_node("create_plan", self._create_plan)
        builder.add_node("exec_plan", self._exec_plan)
        builder.add_node("call_llm", self._call_llm)
        builder.set_entry_point("create_plan")
        logger.debug(f"[{self.agent_type}] Graph 节点已注册")
        return builder

    def _invoke_tools(self, message: AIMessage) -> list:
        tool_calls = message.tool_calls
        tool_messages = []
        logger.info(f"[{self._agent_name}] → LLM 请求调用 {len(tool_calls)} 个工具")
        for idx, tc in enumerate(tool_calls, 1):
            tool_name = tc["name"]
            tool_args = tc["args"]
            tool_id = tc["id"]
            args_summary = str(tool_args)
            if len(args_summary) > 120:
                args_summary = args_summary[:120] + "..."
            logger.info(f"[{self._agent_name}]   工具{idx}: {tool_name}({args_summary})")
            tool_result = None
            for tool in self.tools:
                if tool.name == tool_name:
                    try:
                        tool_result = asyncio.run(tool.ainvoke(tool_args))
                        if isinstance(tool_result, tuple):
                            tool_result = str(tool_result[0])
                    except Exception as e:
                        tool_result = f"工具执行失败: {e}"
                    break
            if tool_result is None:
                tool_result = f"未找到工具: {tool_name}"
            result_short = str(tool_result)[:150].replace("\n", " ")
            logger.info(f"[{self._agent_name}]   结果{idx}: {result_short}")
            if tool_name in ("use_cmd",):
                for keyword, op in [("echo ", "create"), ("> ", "create"), ("mkdir ", "create_dir"),
                                    ("rm ", "delete"), ("move ", "move"), ("copy ", "copy")]:
                    if keyword in str(tool_args.get("cmd", "")):
                        self._record_file_op(str(tool_args.get("cmd", "unknown")), op)
                        break
            tool_messages.append(ToolMessage(content=str(tool_result), tool_call_id=tool_id))
            self._save_message("tool", str(tool_result)[:500])
        return tool_messages

    def _create_plan(self, state: BaseState) -> Command[Literal["exec_plan"]]:
        user_query = state["messages"][-1].content
        logger.info(f"[{self._agent_name}] ══ 阶段1: 制定计划 ══")
        logger.info(f"[{self._agent_name}]   任务: {user_query[:200]}")
        self._save_message("user", user_query)
        plan_prompt = f"""
你是一个任务规划专家。请将用户任务拆解为至少一个简单、可执行的子任务。
规则（必须严格遵守）：
1. 只输出有序任务列表，**不要任何多余解释、开场白、结束语**；
2. 每条任务以「数字+. 」开头，例如：1. 任务内容；
3. 一行一个任务，禁止使用括号、中文序号、特殊符号；
4. 必须生成至少1条任务，严禁空内容。

每个子任务为具体文件/目录操作（创建、删除、新建文件夹、编写文件等）。

{self._history_context}

用户任务：{user_query}

示例输出：
1. 创建文件 hello.py，内容为 print("Hello World")
2. 创建目录 test
3. 将 hello.py 移动到 test 目录下
"""
        messages = [HumanMessage(plan_prompt)]
        for i in range(10):
            logger.debug(f"[{self._agent_name}]   LLM 规划请求 第{i+1}/10 轮")
            response = self.llm.invoke(messages)
            if response.tool_calls:
                logger.info(f"[{self._agent_name}]   规划阶段触发了 {len(response.tool_calls)} 个工具调用")
                messages.append(response)
                messages.extend(self._invoke_tools(response))
                continue
            if not response.content:
                continue
            break
        todos = []
        for line in response.content.strip().split("\n"):
            if line and line[0].isdigit() and "." in line:
                todos.append(line.split(".", 1)[1].strip())
        logger.info(f"[{self._agent_name}]   拆解完成 → {len(todos)} 个子任务")
        return Command(goto="exec_plan", update={
            "task_end": [], "task_plan": todos, "current_step": 0, "task_results": [],
            "messages": [AIMessage(content=f"已拆解为 {len(todos)} 个子任务：\n"
                                        + "\n".join(f"{i+1}. {t}" for i, t in enumerate(todos)))],
        })

    def _exec_plan(self, state: BaseState) -> Command[Literal["call_llm"]]:
        todo_list = state["task_plan"]
        task_results = []
        task_end = []
        messages = list(state["messages"])
        logger.info(f"[{self._agent_name}] ══ 阶段2: 执行计划 ({len(todo_list)} 个子任务) ══")
        for step_index, task_content in enumerate(todo_list):
            step_label = f"步骤 {step_index+1}/{len(todo_list)}"
            logger.info(f"[{self._agent_name}] ── {step_label}: {task_content}")
            exec_prompt = f"""
【当前执行子任务信息】
任务序号：{step_index}
任务内容：{task_content}
历史任务结果：{task_results}

请基于上述子任务，调用对应工具完成该步骤。
如果需要调用工具，请直接输出工具调用。
如果任务已经完成，请返回"success"，
如果任务失败，请返回"fail"。
"""
            messages.append(HumanMessage(content=exec_prompt))
            tool_call_count = 0
            for iter_i in range(20):
                res = self.llm.invoke(messages)
                messages.append(res)
                if res.tool_calls:
                    tool_call_count += len(res.tool_calls)
                    logger.debug(f"[{self._agent_name}]   {step_label} 第{iter_i+1}轮 LLM → {len(res.tool_calls)} 个工具调用")
                    messages.extend(self._invoke_tools(res))
                    continue
                content = res.content.strip().lower() if res.content else ""
                if content and "fail" not in content:
                    task_results.append(f"任务{step_index+1}:{task_content}->success")
                    task_end.append("success")
                    logger.info(f"[{self._agent_name}]   {step_label} ✅ 成功（{iter_i+1}轮LLM, {tool_call_count}次工具调用）")
                else:
                    task_results.append(f"任务{step_index+1}:{task_content}->{res.content}")
                    task_end.append("fail")
                    logger.warning(f"[{self._agent_name}]   {step_label} ❌ 失败 → {res.content[:120]}")
                break
            else:
                task_results.append(f"任务{step_index+1}:{task_content}->超过最大迭代次数")
                task_end.append("failed")
                logger.warning(f"[{self._agent_name}]   {step_label} ⚠ 超迭代（20轮LLM, {tool_call_count}次工具调用）")
        success = sum(1 for s in task_end if s == "success")
        failed = sum(1 for s in task_end if s in ("fail", "failed"))
        logger.info(f"[{self._agent_name}]   执行完成: {success}成功 / {failed}失败 / {len(todo_list)}总")
        self._save_task_result(todo_list, task_results, task_end)
        return Command(goto="call_llm", update={
            "task_plan": todo_list, "current_step": len(todo_list),
            "task_results": task_results, "task_end": task_end, "messages": messages,
        })

    def _call_llm(self, state: BaseState) -> Command[Literal["__end__"]]:
        todo_list = state.get("task_plan", [])
        task_results = state.get("task_results", [])
        task_end = state.get("task_end", [])
        success_count = sum(1 for s in task_end if s == "success")
        failed_count = sum(1 for s in task_end if s == "failed")
        logger.info(f"[{self._agent_name}] ══ 阶段3: 生成验收报告 ══")
        original_task = ""
        for msg in state["messages"]:
            role = getattr(msg, "type", None) or getattr(msg, "role", "")
            if role in ("human", "user"):
                original_task = msg.content
                break
        summary_prompt = f"""你是一个任务汇报助手。请根据以下执行结果，生成一份简洁的任务完成报告。

## 用户原始任务
{original_task}

## 任务计划（共{len(todo_list)}个子任务）
{chr(10).join([f"{i+1}. {t}" for i, t in enumerate(todo_list)]) if todo_list else "无"}

## 执行结果统计
- 总任务数：{len(todo_list)}
- 成功：{success_count}
- 失败：{failed_count}

## 子任务执行详情
{chr(10).join([f"- {r}" for r in task_results]) if task_results else "无"}

请严格按照以下格式输出报告，不要执行任何其他操作：

任务完成报告
1. 任务整体完成情况：[简要说明]
2. 子任务执行状态：[列出各子任务状态]
3. 失败原因（如有）：[说明]
4. 最终结论：[总结]

请只输出报告内容，不要输出任何其他内容。
"""
        res = self.llm.invoke([HumanMessage(content=summary_prompt)])
        report = res.content if res.content and res.content.strip() else "（LLM未返回内容）"
        self._save_message("assistant", report)
        logger.info(f"[{self._agent_name}]   报告已生成（{len(report)} 字符）")
        logger.info(f"[{self._agent_name}] ══ Agent 执行完毕 ══\n")
        return Command(goto="__end__", update={"messages": [res]})

    def run(self, task: str, thread_id: str = "") -> list:
        """执行任务并返回最终消息列表。"""
        tid = thread_id or self.session_id
        _t_start = datetime.now()
        logger.info(f"{'='*60}")
        logger.info(f"[{self._agent_name}] 🚀 启动 run() session={self.session_id} thread={tid}")
        logger.info(f"[{self._agent_name}]   模型={self.model} 工具数={len(self.tools)}")
        logger.info(f"[{self._agent_name}]   任务: {task[:200]}")
        messages = [SystemMessage(content=self.system_prompt), HumanMessage(content=task)]
        history_msgs = self.load_history_messages(limit=20)
        if history_msgs:
            messages = [SystemMessage(content=self.system_prompt)] + history_msgs + [HumanMessage(content=task)]
        initial = {"task_plan": [], "messages": messages, "current_step": 0, "task_results": [], "task_end": []}
        result = self._graph.invoke(initial, {"configurable": {"thread_id": tid}})
        elapsed = (datetime.now() - _t_start).total_seconds()
        logger.info(f"[{self._agent_name}] ⏱ 总耗时: {elapsed:.1f}s")
        return result["messages"]

    def chat(self, message: str = ""):
        """交互式对话。传入 message 执行单轮，不传则进入交互循环。"""
        if message:
            msgs = self.run(message)
            print(f"\n[{self._agent_name}] {(msgs[-1].content if msgs else '（无响应）')}")
            return
        try:
            import readline
        except ImportError:
            try:
                import pyreadline3 as readline
            except ImportError:
                pass
        print(f"\n{'='*60}\n Agent-Hive {self._agent_name}  已就绪\n   会话: {self.session_id}\n{'='*60}\n")
        while True:
            try:
                user_input = input(f"\033[33m[{self._agent_name}] >>>\033[0m ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not user_input:
                continue
            if user_input.lower() in ("/exit", "/quit", "exit", "quit"):
                print(f"[{self._agent_name}] 再见 👋")
                break
            if user_input.lower() in ("/clear", "clear"):
                import shutil
                print("\n" * shutil.get_terminal_size().columns)
                continue
            msgs = self.run(user_input)
            print(f"\n[{self._agent_name}] {(msgs[-1].content if msgs else '（无响应）')}\n")

    def resume(self, thread_id: str = ""):
        """从 Checkpoint 中断点恢复执行。"""
        tid = thread_id or self.session_id
        logger.info(f"[{self.agent_type}] resume() thread={tid}")
        return self._graph.invoke(None, {"configurable": {"thread_id": tid}})

    def get_checkpoint_history(self, thread_id: str = ""):
        tid = thread_id or self.session_id
        return list(self._graph.get_state_history({"configurable": {"thread_id": tid}}))
