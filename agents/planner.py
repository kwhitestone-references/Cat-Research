"""
PlannerAgent - 研究规划智能体
负责将用户问题分解为可执行的研究子任务
"""
import config as _config
from agents.base_agent import BaseAgent
from config import PLANNER_MODEL


def _build_planner_system_prompt() -> str:
    y      = _config.CURRENT_YEAR
    y1     = _config.PREV_YEAR
    today  = _config.CURRENT_DATE_STR
    d3m    = _config.DATE_3M_AGO_STR
    d6m    = _config.DATE_6M_AGO_STR
    d3m_iso = _config.DATE_3M_AGO_ISO
    d6m_iso = _config.DATE_6M_AGO_ISO
    return f"""你是一位资深的研究规划专家，专门负责设计高质量、多语言、时效性强的研究方案。

## 你的职责
给定一个研究问题，你需要：
1. 深入分析问题的各个维度和所属领域
2. 设计全面的研究计划，覆盖所有重要方面
3. 将任务分解为具体可执行的搜索查询（分时效层次和语言）
4. 规划研究的优先级和逻辑顺序

## 工作流程
1. 首先读取会话文件了解问题背景
2. 判断话题所属领域（科技/政策/经济/社会/学术等）和地域范围
3. 设计 10-16 个具体的搜索查询，按时效分层、按语言分布
4. 将计划以结构化 JSON 格式保存到指定文件

## 时效分层原则（必须严格执行）
今天是 **{today}**，默认研究窗口 **{d6m} 至今**（近6个月）。

### 三级时间窗口
| 层次 | 日期范围 | 优先级 | 占比要求 | 搜索词要求 |
|------|----------|--------|----------|------------|
| **优先层**（近3个月）| {d3m} 至 {today} | high | ≥50% | 必须包含具体月份或 "latest" "最新" |
| **补充层**（3-6个月）| {d6m} 至 {d3m} | medium | ≤30% | 含年份 "{y}" 或具体月份 |
| **背景层**（>6个月）| {d6m_iso} 之前 | low | ≤20% | 仅在用户明确要求历史时才加入 |

**规则**：
- 搜索词中直接嵌入日期范围（如 "after:{d6m_iso}"），让搜索引擎过滤
- 背景层查询仅在澄清摘要中 timeframe 明确超出6个月时才规划
- 否则不得安排背景层查询

## 多语言原则（必须执行）
根据话题领域合理分配语言：
- **科技/AI/工程**：60%+ 英文查询（GitHub、arXiv、技术媒体）+ 中文查询（国内进展）
- **政策/法规/经济**：中英文各半，并考虑相关地区本地语言
- **文化/社会**：以中文为主，辅以英文国际视角
- **全球性话题**：中英文各半，尽量加入其他语言关键词
- 搜索词要根据语言习惯自然书写，不要生硬翻译

## 研究计划格式
```json
{{
  "question": "原始问题",
  "objective": "研究目标",
  "domain": "话题领域（科技/政策/经济/社会等）",
  "key_aspects": ["方面1", "方面2", ...],
  "search_queries": [
    {{
      "query": "搜索词（自然语言，对应语言书写）",
      "purpose": "为什么搜索这个",
      "priority": "high/medium/low",
      "time_layer": "recent / mid / background",
      "language": "zh / en / other",
      "category": "分类（最新进展/数据统计/政策法规/案例/学术/观点争议等）"
    }}
  ],
  "expected_output": "期望输出的形式和内容描述",
  "depth_requirement": "研究深度要求"
}}
```

## 质量要求
- 搜索查询要多样化，覆盖不同角度、不同时效、不同语言
- 考虑历史、现状、趋势、争议等多个维度
- 确保近期信息（3个月内）在计划中占最高优先级
- 不能将搜索局限于单一语言圈，尤其是科技类话题必须包含英文"""


PLANNER_SYSTEM_PROMPT = _build_planner_system_prompt()


class PlannerAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="规划师",
            system_prompt=PLANNER_SYSTEM_PROMPT,
            model=PLANNER_MODEL
        )

    def create_plan(self, workspace: str, clarified_question: str,
                    research_strategy: str = None) -> dict:
        """
        创建研究计划
        返回计划的 Python 字典对象
        """
        import json
        import os

        plan_file = os.path.join(workspace, "03_plan.json")

        strategy_block = ""
        if research_strategy and research_strategy.strip():
            strategy_block = f"""
## 研究策略（用户指定，必须遵守）
{research_strategy.strip()}

"""

        task = f"""【今天是 {_config.CURRENT_DATE_STR}，近期层搜索词必须包含 "{_config.CURRENT_YEAR}" 或 "latest {_config.CURRENT_YEAR}"】

请为以下研究问题制定详细的研究计划。

## 研究问题
{clarified_question}
{strategy_block}
## 你的任务
1. 仔细分析这个问题，识别所有重要的研究维度
2. 设计 10-15 个高质量的搜索查询，覆盖：
   - 基础背景和定义
   - 当前状态和最新发展
   - 关键数据和统计
   - 重要案例和实例
   - 专家观点和分析
   - 争议点或不同角度
   - 未来趋势或建议
3. 将完整计划以 JSON 格式保存到：{plan_file}

重要：必须使用 write_file 工具将计划保存到文件，然后返回计划摘要。"""

        result = self.run(task)

        # 尝试读取保存的计划文件
        from tools.file_tools import read_json
        plan = read_json(plan_file)
        if "error" in plan and len(plan.get("raw", "")) < 10:
            # 如果文件读取失败，创建基础计划
            plan = self._create_fallback_plan(clarified_question, plan_file)

        return plan

    def _create_fallback_plan(self, question: str, plan_file: str) -> dict:
        """当智能体未能正确创建计划时的备用方案"""
        import json
        from tools.file_tools import write_json

        plan = {
            "question": question,
            "objective": f"深入研究和分析：{question}",
            "key_aspects": ["背景介绍", "核心内容", "现状分析", "影响因素", "未来展望"],
            "search_queries": [
                {"query": f"{question} 最新 after:{_config.DATE_3M_AGO_ISO}", "purpose": "近3个月最新动态", "priority": "high", "time_layer": "recent3m", "language": "zh", "category": "最新进展"},
                {"query": f"{question} latest after:{_config.DATE_3M_AGO_ISO}", "purpose": "近3个月英文资讯", "priority": "high", "time_layer": "recent3m", "language": "en", "category": "最新进展"},
                {"query": f"{question} 进展 after:{_config.DATE_6M_AGO_ISO}", "purpose": "近6个月进展", "priority": "high", "time_layer": "recent6m", "language": "zh", "category": "现状"},
                {"query": f"{question} news after:{_config.DATE_6M_AGO_ISO}", "purpose": "近6个月英文新闻", "priority": "medium", "time_layer": "recent6m", "language": "en", "category": "现状"},
                {"query": f"{question} 分析报告", "purpose": "专业分析", "priority": "medium", "time_layer": "recent6m", "language": "zh", "category": "分析"},
                {"query": f"{question} data statistics {_config.CURRENT_YEAR}", "purpose": "数据统计", "priority": "medium", "time_layer": "recent6m", "language": "en", "category": "数据"},
                {"query": f"{question} 背景 历史", "purpose": "历史背景（仅用于上下文）", "priority": "low", "time_layer": "background", "language": "zh", "category": "背景"},
            ],
            "expected_output": "全面的研究报告",
            "depth_requirement": "深入分析，有数据支撑，有具体案例"
        }
        write_json(plan_file, plan)
        return plan
