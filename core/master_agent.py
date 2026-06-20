"""MasterAgent — 根节点 Agent，负责任务拆分、子 Agent 管理、结果验收。"""
from typing import Optional

from core.base_agent import BaseAgent, BaseState
from core.config import AgentConfig
from core.worker_agent import WorkerAgent

system_prompt = """
你是 MasterAgent（根节点），负责将复杂项目拆分为多个独立模块，创建子 Agent 执行，
并最终验收所有子任务结果。

工作流程：
1. 使用 create_sub_agent 为每个模块创建专属子 Agent
2. 给每个子 Agent 下达具体任务（调用 agent.run(task)）
3. 等待所有子 Agent 完成后，汇总结果并生成验收报告

注意：如果子模块仍然太复杂，子 Agent 可以继续创建它的子 Agent（树高上限5层）。
"""


class MasterState(BaseState):
    pass


class MasterAgent(BaseAgent):
    def __init__(self, tools, system_prompt="", config: Optional[AgentConfig] = None):
        super().__init__(
            state=MasterState, tools=tools,
            system_prompt=system_prompt or globals().get("system_prompt", ""),
            agent_type="master", session_id="", depth=0, parent_id="", config=config,
        )
        self._restore_workers()

    def _restore_workers(self):
        """从 SQLite 恢复持久化的 Worker 元数据，重建 worker_dict。"""
        count = 0
        for row in self.memory.get_all_workers():
            if row["parent_id"] and row["parent_id"] != self._agent_name:
                continue
            name = row["name"]
            worker = WorkerAgent(state=BaseState, name=name, tools=self.tools,
                                 system_prompt=row["system_prompt"] or "",
                                 session_id=row["session_id"],
                                 depth=row["depth"] or 1, parent_id=row["parent_id"] or "",
                                 config=self.config)
            self.worker_dict[name] = {
                "worker": worker, "system_prompt": row["system_prompt"],
                "tools": self.tools, "tasks": row["task_summary"] or "当前 worker 没有任务",
                "depth": row["depth"] or 1, "parent": row["parent_id"] or "",
            }
            count += 1
        if count:
            print(f"从 SQLite 恢复 {count} 个子 Agent")

    def run(self, task: str, thread_id: str = "") -> list:
        return super().run(task, thread_id)

    def resume(self, thread_id: str = ""):
        return super().resume(thread_id)
