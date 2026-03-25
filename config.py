"""
猫叔的深思熟虑 - 全局配置
"""
import os
import json
from datetime import datetime
from urllib.parse import urlparse, urlunparse
from dotenv import load_dotenv

load_dotenv()


# === 网络时间（启动时从互联网获取，多重备选）===
def _fetch_network_time() -> datetime:
    """从网络获取当前时间，依次尝试多个源，失败则使用系统时间"""
    import requests
    from email.utils import parsedate_to_datetime

    # 方案1: worldtimeapi（境外可用）
    try:
        r = requests.get("http://worldtimeapi.org/api/ip", timeout=3)
        dt_str = r.json().get("datetime", "")[:19]
        return datetime.fromisoformat(dt_str)
    except Exception:
        pass

    # 方案2: 苏宁时间 API（国内可用）
    try:
        r = requests.get("https://quan.suning.com/getSysTime.do", timeout=3)
        ts = r.json().get("sysTime2", "")  # 格式: "2026-03-21 14:30:00"
        if ts:
            return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    # 方案3: 读取 HTTP 响应头 Date 字段
    for url in ["https://www.baidu.com", "https://www.bing.com"]:
        try:
            r = requests.head(url, timeout=3)
            date_str = r.headers.get("Date", "")
            if date_str:
                return parsedate_to_datetime(date_str).replace(tzinfo=None)
        except Exception:
            pass

    # 最终备选：系统时间
    print("  [init] Network time unavailable, using system time.", flush=True)
    return datetime.now()


def _months_ago(dt: datetime, months: int) -> datetime:
    """计算 N 个月前的日期，处理月末溢出"""
    import calendar
    total_months = dt.year * 12 + (dt.month - 1) - months
    year, month = divmod(total_months, 12)
    month += 1
    max_day = calendar.monthrange(year, month)[1]
    return dt.replace(year=year, month=month, day=min(dt.day, max_day))


print("[init] Fetching current time from network...", flush=True)
CURRENT_DATETIME: datetime = _fetch_network_time()
CURRENT_DATE_STR: str    = CURRENT_DATETIME.strftime("%Y年%m月%d日")
CURRENT_DATE_ISO: str    = CURRENT_DATETIME.strftime("%Y-%m-%d")
CURRENT_YEAR: int        = CURRENT_DATETIME.year
PREV_YEAR: int           = CURRENT_YEAR - 1
PREV2_YEAR: int          = CURRENT_YEAR - 2
CURRENT_YEAR_HALF: str   = (
    f"{CURRENT_YEAR}年上半年" if CURRENT_DATETIME.month <= 6
    else f"{CURRENT_YEAR}年下半年"
)

# 精确日期窗口
DATE_3M_AGO: datetime = _months_ago(CURRENT_DATETIME, 3)
DATE_6M_AGO: datetime = _months_ago(CURRENT_DATETIME, 6)
DATE_3M_AGO_STR: str  = DATE_3M_AGO.strftime("%Y年%m月%d日")
DATE_6M_AGO_STR: str  = DATE_6M_AGO.strftime("%Y年%m月%d日")
DATE_3M_AGO_ISO: str  = DATE_3M_AGO.strftime("%Y-%m-%d")
DATE_6M_AGO_ISO: str  = DATE_6M_AGO.strftime("%Y-%m-%d")

print(f"[init] Current date : {CURRENT_DATE_STR}", flush=True)
print(f"[init] 3-month cutoff: {DATE_3M_AGO_STR}", flush=True)
print(f"[init] 6-month cutoff: {DATE_6M_AGO_STR}", flush=True)

# === 持久化设置文件（用户通过 UI 设置的 API Key 等保存于此）===
_SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "settings.json")

def _load_settings_file() -> dict:
    """加载 settings.json，不存在则返回空 dict"""
    if os.path.exists(_SETTINGS_FILE):
        try:
            with open(_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_settings(data: dict):
    """将设置持久化到 settings.json"""
    existing = _load_settings_file()
    existing.update(data)
    with open(_SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


def normalize_openai_base_url(value: str) -> str:
    """Normalize OpenAI-compatible base URLs so bare hosts default to /v1."""
    raw = (value or "").strip()
    if not raw:
        return raw

    trimmed = raw.rstrip("/")
    try:
        parsed = urlparse(trimmed)
    except Exception:
        return trimmed

    path = (parsed.path or "").rstrip("/")
    if not path:
        path = "/v1"

    return urlunparse(parsed._replace(path=path, params="", query="", fragment=""))

# 加载持久化设置（优先级：环境变量 > settings.json > 空）
_saved = _load_settings_file()

# === OpenAI 兼容 API 配置 ===
# 兼容任何 OpenAI-compatible 接口（OpenAI / 智谱 / DeepSeek / 本地 Ollama 等）
API_KEY  = (os.environ.get("ZHIPU_API_KEY", "")
            or os.environ.get("OPENAI_API_KEY", "")
            or _saved.get("api_key", ""))
API_BASE_URL = normalize_openai_base_url(
    os.environ.get("ZHIPU_BASE_URL", "")
    or os.environ.get("OPENAI_BASE_URL", "")
    or _saved.get("base_url", "")
    or "https://open.bigmodel.cn/api/paas/v4/"
)

# 向后兼容别名
ZHIPU_API_KEY  = API_KEY
ZHIPU_BASE_URL = API_BASE_URL
ANTHROPIC_API_KEY = API_KEY

# === 模型配置 ===
# 【核心模型】负责推理、规划、研究、分析、写作——对质量影响最大
CORE_MODEL = (os.environ.get("CORE_MODEL", "")
              or _saved.get("core_model", "")
              or "glm-4.7")
ORCHESTRATOR_MODEL       = CORE_MODEL
PLANNER_MODEL            = CORE_MODEL
RESEARCHER_MODEL         = CORE_MODEL
ANALYST_MODEL            = CORE_MODEL
WRITER_MODEL             = CORE_MODEL

# 【辅助模型】负责评审、来源验证、事实核查、结论验证
SUPPORT_MODEL = (os.environ.get("SUPPORT_MODEL", "")
                 or _saved.get("support_model", "")
                 or "glm-4.7-flash")
CRITIC_MODEL                 = SUPPORT_MODEL
SOURCE_VERIFIER_MODEL        = SUPPORT_MODEL
FACT_CHECKER_MODEL           = SUPPORT_MODEL
CONCLUSION_VALIDATOR_MODEL   = SUPPORT_MODEL

# === 工作空间配置 ===
WORKSPACE_DIR = os.path.join(os.path.dirname(__file__), "workspace")

# === 研究配置 ===
MAX_IMPROVEMENT_CYCLES = 5         # 最多改进循环次数
MIN_IMPROVEMENT_CYCLES = 2         # 强制最少2次
MAX_AGENT_TURNS = 40               # 单个智能体最大交互轮数
MAX_SEARCH_RESULTS = 8             # 每次搜索最多返回结果数
MAX_FETCH_CHARS = 6000             # 每个网页最多提取字符数
QUALITY_THRESHOLD = 8.0            # 质量阈值（满分10分），高于此值才可提前结束

# === 显示配置 ===
SHOW_AGENT_THOUGHTS = True         # 是否显示智能体工作细节
SEPARATOR = "=" * 70

# === 上下文压缩配置 ===
# 单个智能体对话超过此字符数时自动压缩（约 30k token，每字符约 4 字节）
COMPRESS_THRESHOLD_CHARS = int(os.environ.get("COMPRESS_THRESHOLD_CHARS", "100000"))
# 压缩时保留最近 N 条消息（不纳入压缩，保持 reasoning_content 链完整）
COMPRESS_KEEP_RECENT = int(os.environ.get("COMPRESS_KEEP_RECENT", "6"))

# === 子进程隔离配置 ===
# 是否对长运行阶段启用独立子进程（进程隔离、上下文独立）
USE_SUBPROCESS = os.environ.get("USE_SUBPROCESS", "false").lower() == "true"
# 哪些智能体使用子进程（逗号分隔，空字符串=全部）
SUBPROCESS_AGENTS = [a.strip() for a in os.environ.get("SUBPROCESS_AGENTS", "researcher,analyst,writer").split(",") if a.strip()]
