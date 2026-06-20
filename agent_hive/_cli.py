"""CLI 入口：加载 .env，启动交互式对话。"""
from dotenv import load_dotenv

from core.config import AgentConfig
from core.master_agent import MasterAgent
from core.tools import get_tools


def main():
    load_dotenv()
    config = AgentConfig()
    tools = get_tools(config.mcp_servers_path)
    agent = MasterAgent(tools=tools, config=config)
    agent.chat()


if __name__ == "__main__":
    main()
