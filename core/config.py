"""统一配置管理，支持 .env / 环境变量 / 直接传参"""
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


class AgentConfig(BaseSettings):
    """Agent 框架统一配置，Worker LLM 不设则复用 Master 配置。"""

    openai_api_key: str = ""
    openai_base_url: str = ""
    llm_model: str = "gpt-4"

    worker_agent_url: str = ""
    worker_agent_key: str = ""
    worker_llm_model: str = ""

    data_dir: str = ".code-agent"
    mcp_servers_file: str = "mcp_servers.json"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def mcp_servers_path(self) -> Path:
        return self.data_path / self.mcp_servers_file

    @property
    def memory_db_path(self) -> Path:
        return self.data_path / "memory.db"

    @property
    def checkpoint_db_path(self) -> Path:
        return self.data_path / "checkpoints.db"

    @property
    def worker_base_url(self) -> str:
        return self.worker_agent_url or self.openai_base_url

    @property
    def worker_api_key(self) -> str:
        return self.worker_agent_key or self.openai_api_key

    @property
    def worker_model(self) -> str:
        return self.worker_llm_model or self.llm_model
