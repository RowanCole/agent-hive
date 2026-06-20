"""安全校验 — 命令白名单、路径白名单。"""
from pathlib import Path
from typing import Optional

from utils.log import getLogger

logger = getLogger("security")

safe_commands = {
    "dir", "cd", "type", "echo", "copy", "move", "del", "mkdir", "rmdir",
    "python", "pip", "git", "tree", "find", "where", "ren"
}

dangerous_commands = {
    "format", "del", "rm", "rd", "erase", "shutdown", "restart", "taskkill",
    "systeminfo", "net", "reg", "attrib", "cacls", "icacls", "chkdsk", "sfc"
}

allowed_dirs = {Path.cwd(), Path.cwd() / "output", Path.cwd() / "workspace"}


def is_command_safe(cmd: str) -> bool:
    cmd_parts = cmd.strip().split()
    if not cmd_parts:
        return False
    if cmd_parts[0].lower() in dangerous_commands:
        logger.warning(f"危险指令拦截: {cmd}")
        return False
    return True


def is_path_allowed(file_path: str) -> bool:
    try:
        abs_path = Path(file_path).resolve()
        return any(str(abs_path).startswith(str(d.resolve()))
                   for d in allowed_dirs)
    except Exception as e:
        logger.error(f"路径安全校验异常: {e}")
        return False


def validate_file_path(file_path: str, operation: str = "access") -> Optional[str]:
    if not is_path_allowed(file_path):
        return f"错误：路径不在允许范围内: {file_path}"
    return None


def validate_command(cmd: str) -> Optional[str]:
    if not is_command_safe(cmd):
        return f"错误：命令不在安全白名单中: {cmd}"
    return None
