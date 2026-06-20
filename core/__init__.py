"""
Agent Hive — 基于 LangGraph + MCP 的多 Agent 分层协作框架

使用方式：
    from agent_hive import MasterAgent, AgentConfig

    config = AgentConfig(_env_file=".env")
    agent = MasterAgent(config=config)
    agent.chat()
"""

from core.base_agent import BaseAgent, BaseState
from core.master_agent import MasterAgent
from core.worker_agent import WorkerAgent
from core.config import AgentConfig
from core.tools import tools_list, get_tools

__all__ = [
    "BaseAgent",
    "BaseState",
    "MasterAgent",
    "WorkerAgent",
    "AgentConfig",
    "tools_list",
    "get_tools",
]
