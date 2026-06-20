"""Agent Hive — 多 Agent 分层协作框架

用法：
    python main.py                        # 交互模式
    python main.py "你的任务描述"          # 单次执行
    python main.py --no-mcp               # 不加载 MCP 工具
"""
import argparse
import sys

from dotenv import load_dotenv

from core.config import AgentConfig
from core.master_agent import MasterAgent
from core.tools import get_tools

VERSION = "0.1.0"


def print_banner():
    print(rf"""
  ╔══════════════════════════════════════════╗
  ║           Agent Hive  v{VERSION}         ║
  ╚══════════════════════════════════════════╝
    """)


def print_config_summary(config: AgentConfig):

    print(f"  │ Master 模型 : {config.llm_model}")
    print(f"  │ Master 地址 : {config.openai_base_url or '(默认)'}")
    if config.worker_model != config.llm_model:
        print(f"  │ Worker 模型 : {config.worker_model}")
    print(f"  │ MCP 配置    : {config.mcp_servers_path}")
    print(f"  │ 数据目录    : {config.data_path.resolve()}")



def validate_env(config: AgentConfig) -> bool:
    issues = []
    if not config.openai_api_key:
        issues.append("OPENAI_API_KEY 未设置")
    if not config.openai_base_url:
        issues.append("OPENAI_BASE_URL 未设置")
    if issues:
        print("  ⚠ 环境配置检查：")
        for issue in issues:
            print(f"    • {issue}")
        print("    请在 .env 文件中配置或设置环境变量\n")
        return False
    return True


def main():
    load_dotenv()
    config = AgentConfig()

    parser = argparse.ArgumentParser(
        description="Agent Hive — 多 Agent 分层协作框架",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n  python main.py                           # 交互模式\n  python main.py 搜索AI新闻并保存到文件       # 单次执行\n  python main.py --no-mcp                  # 不加载 MCP 工具",
    )
    parser.add_argument("task", nargs="?", default="", help="任务描述（不传则进入交互模式）")
    parser.add_argument("--no-mcp", action="store_true", help="跳过 MCP 工具加载")
    parser.add_argument("--version", action="store_true", help="显示版本号")
    args = parser.parse_args()

    if args.version:
        print(f"Agent Hive v{VERSION}")
        return

    print_banner()
    print_config_summary(config)
    validate_env(config)

    tools = get_tools() if args.no_mcp else get_tools(config.mcp_servers_path)
    if args.no_mcp:
        print("  ℹ MCP 工具已跳过（--no-mcp）\n")

    try:
        agent = MasterAgent(tools=tools, config=config)
    except Exception as e:
        print(f"\n  ❌ Agent 初始化失败: {e}")
        sys.exit(1)

    if args.task:
        print(f"\n  ▶ 任务: {args.task[:200]}")
        print("  ────────────────────────────────────────")
        try:
            msgs = agent.run(args.task)
            print(f"\n  📋 结果:\n{(msgs[-1].content if msgs else '（无响应）')}\n")
        except KeyboardInterrupt:
            print("\n  ⚡ 任务已取消\n")
        except Exception as e:
            print(f"\n  ❌ 执行失败: {e}\n")
        return

    try:
        agent.chat()
    except KeyboardInterrupt:
        print("\n  👋 再见\n")
    except Exception as e:
        print(f"\n  ❌ 异常退出: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
