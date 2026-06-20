"""内置工具 + MCP 工具按需加载。"""
import asyncio
import json
import subprocess
from pathlib import Path
from typing import Annotated, Optional

from langchain_core.tools import tool
from langchain_mcp_adapters.tools import load_mcp_tools
from utils.log import getLogger

logger = getLogger("tools")


def _load_mcp_servers(mcp_servers_path: Path) -> dict:
    if not mcp_servers_path.exists():
        logger.info(f"MCP 配置文件不存在: {mcp_servers_path}，跳过 MCP 工具加载")
        return {}
    try:
        raw = json.loads(mcp_servers_path.read_text(encoding="utf-8"))
        config = raw.get("mcpServers", raw)
        if not isinstance(config, dict):
            logger.warning(f"MCP 配置格式错误: {mcp_servers_path}")
            return {}
        return config
    except Exception as e:
        logger.warning(f"加载 MCP 配置失败: {e}")
        return {}


async def _load_all_mcp_tools(mcp_servers_path: Path):
    mcp_config = _load_mcp_servers(mcp_servers_path)
    all_tools = []
    for server_name, cfg in mcp_config.items():
        url = cfg.get("url", "").strip()
        if not url or cfg.get("type") != "streamable_http":
            continue
        try:
            connection = {"transport": "streamable_http", "url": url}
            tools = await load_mcp_tools(None, connection=connection, server_name=server_name,
                                         tool_name_prefix=(len(mcp_config) > 1))
            all_tools.extend(tools)
            logger.info(f"MCP {server_name}: 已加载 {len(tools)} 个工具")
        except Exception as e:
            logger.warning(f"MCP {server_name}: 不可用 ({e})")
    return all_tools


@tool
def use_cmd(cmd: Annotated[str, "需要执行的命令"]) -> str:
    """执行一条系统命令，返回 stdout 和 stderr。"""
    logger.debug(f"use_cmd: {cmd}")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                            errors="ignore", shell=True, timeout=3600)
    return result.stdout, result.stderr


@tool
def write_file(path: Annotated[str, "文件路径（相对于当前工作目录）"],
               content: Annotated[str, "完整文件内容"]) -> str:
    """写入文件，自动创建父目录。"""
    fp = Path(path)
    fp.parent.mkdir(parents=True, exist_ok=True)
    encoding = "gbk" if fp.suffix in (".bat", ".cmd") else "utf-8"
    fp.write_text(content, encoding=encoding)
    logger.debug(f"write_file: {path} ({fp.stat().st_size} bytes)")
    return f"OK: {path} ({fp.stat().st_size} bytes)"


@tool
def read_file(path: Annotated[str, "文件路径（相对于当前工作目录）"]) -> str:
    """读取文件内容。"""
    fp = Path(path)
    if not fp.exists():
        return f"文件不存在: {path}"
    encoding = "gbk" if fp.suffix in (".bat", ".cmd") else "utf-8"
    try:
        content = fp.read_text(encoding=encoding)
        if len(content) <= 6000:
            return content
        return content[:6000] + f"\n...（输出截断，文件共 {fp.stat().st_size} 字节）"
    except UnicodeDecodeError:
        return fp.read_text(encoding="gbk", errors="replace")


tools_list = [write_file, read_file]


def get_tools(mcp_servers_path: Optional[Path] = None) -> list:
    """获取工具列表，传入 MCP 配置路径时自动加载 MCP 工具。"""
    import core.tools as _t
    if mcp_servers_path is None:
        return _t.tools_list
    mcp_tools = asyncio.run(_load_all_mcp_tools(mcp_servers_path))
    logger.info(f"MCP 工具总计: {len(mcp_tools)} 个")
    return _t.tools_list + mcp_tools
