"""WorkerAgent — 执行父 Agent 分配的子任务，可递归创建下层 Worker。"""
from typing import Optional

from core.base_agent import BaseAgent, BaseState
from core.config import AgentConfig


class WorkerAgent(BaseAgent):
    def __init__(self, state: type[BaseState] = BaseState,
                 name: str = "worker",
                 tools: list = [],
                 system_prompt: str = "",
                 session_id: str = "",
                 depth: int = 1,
                 parent_id: str = "",
                 config: Optional[AgentConfig] = None):
        super().__init__(
            state=state,
            tools=tools,
            system_prompt=system_prompt,
            agent_type="worker",
            session_id=session_id,
            depth=depth,
            parent_id=parent_id,
            config=config,
        )
        self.name = name

    def add_tool(self, tool):
        """动态添加工具并重新绑定 LLM。"""
        self.tools.append(tool)
        self.llm = self.llm.bind_tools(self.tools)
