"""
多智能体研究系统 - 主入口
Multi-Agent Research System

使用方法：
  python main.py                    # 交互模式
  python main.py "你的研究问题"     # 直接提问模式
"""
import os
import sys
import time

# Windows GBK 控制台 emoji 兼容
import io
try:
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
except Exception:
    pass

# 检查 Python 版本
if sys.version_info < (3, 9):
    print("❌ 需要 Python 3.9 或更高版本")
    sys.exit(1)


def check_environment():
    """检查运行环境是否满足要求"""
    errors = []
    warnings = []

    # 检查 API Key
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        # 尝试从 .env 文件加载
        try:
            from dotenv import load_dotenv
            load_dotenv()
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        except ImportError:
            pass

    if not api_key:
        errors.append("未设置 ANTHROPIC_API_KEY 环境变量")

    # 检查必要的包
    required_packages = {
        "anthropic": "pip install anthropic",
        "duckduckgo_search": "pip install duckduckgo-search",
        "bs4": "pip install beautifulsoup4",
        "requests": "pip install requests",
    }

    missing = []
    for package, install_cmd in required_packages.items():
        try:
            __import__(package)
        except ImportError:
            missing.append(f"  - {package}: {install_cmd}")

    if missing:
        errors.append("缺少必要的 Python 包：\n" + "\n".join(missing))
        errors.append("请运行：pip install -r requirements.txt")

    return errors, warnings


def print_banner():
    """打印系统横幅"""
    banner = """
╔══════════════════════════════════════════════════════════════════════╗
║                    🔬 多智能体研究系统                              ║
║                 Multi-Agent Research System v1.0                    ║
╠══════════════════════════════════════════════════════════════════════╣
║  智能体配置：                                                        ║
║  📋 规划师 → 🔍 研究员 → 🧐 分析师 → ✍️ 写作者 → 🔄 评审员(5+次)  ║
║                                                                      ║
║  特性：自动搜索 | 多源研究 | 深度分析 | 5轮+质量改进 | 文件通信     ║
╚══════════════════════════════════════════════════════════════════════╝
"""
    print(banner, flush=True)


def get_question() -> str:
    """获取用户的研究问题"""
    # 命令行参数模式
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        print(f"\n📌 研究问题（来自命令行）：{question}", flush=True)
        return question

    # 交互模式
    print("\n" + "─" * 70, flush=True)
    print("💬 请输入您想要研究的问题：", flush=True)
    print("   （可以是任何话题：技术、商业、科学、历史、社会等）", flush=True)
    print("─" * 70, flush=True)

    while True:
        try:
            question = input("\n🔍 您的问题 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 再见！")
            sys.exit(0)

        if question:
            return question
        else:
            print("❓ 请输入一个问题", flush=True)


def display_final_report(report: str, workspace: str):
    """显示最终报告"""
    print(f"\n{'═'*70}", flush=True)
    print("📄 最终研究报告", flush=True)
    print(f"{'═'*70}", flush=True)

    # 限制控制台显示长度
    max_display = 5000
    if len(report) > max_display:
        print(report[:max_display], flush=True)
        print(f"\n... [报告过长，仅显示前 {max_display} 字符]", flush=True)
    else:
        print(report, flush=True)

    print(f"\n{'═'*70}", flush=True)
    print(f"📁 完整报告保存在：{workspace}", flush=True)

    # 询问是否要显示完整报告
    try:
        show_full = input("\n是否显示完整报告路径？(y/n) > ").strip().lower()
        if show_full == 'y':
            final_file = os.path.join(workspace, "09_final.md")
            print(f"\n完整报告文件：{final_file}", flush=True)
    except (EOFError, KeyboardInterrupt):
        pass


def main():
    """主函数"""
    print_banner()

    # === 环境检查 ===
    print("🔎 检查运行环境...", flush=True)
    errors, warnings = check_environment()

    if errors:
        print("\n❌ 环境检查失败：", flush=True)
        for err in errors:
            print(f"  • {err}", flush=True)
        print("\n请解决以上问题后重新运行。", flush=True)
        sys.exit(1)

    if warnings:
        for warn in warnings:
            print(f"  ⚠️  {warn}", flush=True)

    print("✅ 环境检查通过", flush=True)

    # === 获取研究问题 ===
    question = get_question()

    # === 确认开始 ===
    print(f"\n{'─'*70}", flush=True)
    print(f"📌 将要研究：{question}", flush=True)
    print(f"⚙️  设置：最少 5 轮质量改进，使用 claude-opus-4-6 模型", flush=True)
    print(f"⏱️  预计时间：10-20 分钟（取决于问题复杂度）", flush=True)

    try:
        confirm = input("\n确认开始研究？(y/n) > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        confirm = "y"

    if confirm not in ('y', 'yes', '是', '确认', ''):
        print("已取消。", flush=True)
        sys.exit(0)

    # === 执行研究 ===
    start_time = time.time()

    try:
        from orchestrator import ResearchOrchestrator

        orchestrator = ResearchOrchestrator()
        report = orchestrator.run(question)

        elapsed = time.time() - start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)

        print(f"\n⏱️  总耗时：{minutes} 分 {seconds} 秒", flush=True)

        # 显示最终报告
        display_final_report(report, orchestrator.workspace)

    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        print(f"\n\n⚠️  研究被用户中断（已运行 {elapsed:.0f} 秒）", flush=True)
        print("部分结果可能已保存在工作空间中。", flush=True)
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 研究过程中出现错误：{str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
