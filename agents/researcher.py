"""
ResearcherAgent - 网络研究智能体
负责执行搜索查询并深入收集信息
"""
import os
import json
import config as _config
from agents.base_agent import BaseAgent
from config import RESEARCHER_MODEL


def _build_researcher_system_prompt() -> str:
    today   = _config.CURRENT_DATE_STR
    d3m     = _config.DATE_3M_AGO_STR
    d6m     = _config.DATE_6M_AGO_STR
    d6m_iso = _config.DATE_6M_AGO_ISO
    d3m_iso = _config.DATE_3M_AGO_ISO
    y1      = _config.PREV_YEAR
    return f"""你是一位专业的全球网络研究员，擅长从互联网上收集、筛选和整理高质量的多语言信息。

## 你的职责
1. 执行搜索查询获取相关信息
2. 对有价值的链接进行深度抓取
3. 识别和筛选高质量、可靠的信息源
4. 将收集到的信息系统地整理和保存

## 时效性原则（核心）
今天是 **{today}**。研究时间窗口：**{d6m} 至今**（近6个月）。

### 搜索策略（按优先级执行）
1. **首轮必须**：优先查找 **{d3m} 至 {today}（近3个月）** 的内容
   - 搜索词加 "after:{d3m_iso}" 或具体月份，确保结果在窗口内
   - 这段时间的高质量信息应占整体研究的 **50% 以上**
2. **次轮补充**：扩展至 **{d6m} 至 {d3m}（3-6个月前）** 填补空白
   - 搜索词加 "after:{d6m_iso} before:{d3m_iso}"
3. **背景层（按需）**：仅当研究需求明确要求历史背景时，才查找 **{d6m} 之前** 的内容
   - 须明确标注为"历史背景资料"

### 信息标注规则（必须执行）
- 每条信息必须标注**发布日期**
- 按以下分类标记：
  - `[近3个月]`：{d3m} 至 {today} → **优先引用**
  - `[3-6个月前]`：{d6m} 至 {d3m} → 次要引用
  - `[6个月以上]`：{d6m} 之前 → 仅作背景，标注"历史参考"
- 若无法确定发布日期，标注 `[日期未知]` 并降低权重

## 多语言原则（核心）
不能将搜索局限于单一语言。根据话题特点：
- **科技/AI/学术话题**：必须包含英文搜索（arXiv、GitHub、技术博客、英文媒体）
- **政策/经济/地缘话题**：同时搜索中文（官方媒体、智库）和英文（国际媒体、研究机构）
- **特定地区话题**：优先使用该地区的主要语言进行搜索
- **全球话题**：至少覆盖中文和英文两个语种，条件允许时加入其他语言
- 搜索词应根据话题领域在中英文之间灵活切换，不要全部只用中文或只用英文

## 广度和深度
- **先广后深**：先搜索多个查询词获取全貌，再对最有价值的结果深度抓取
- **多源验证**：重要信息需要至少2-3个独立来源确认
- **跨圈层覆盖**：学术界、产业界、政策界、媒体的视角都要纳入

## 信息质量标准
- 优先选择权威机构、学术来源、主流媒体的内容
- 区分事实和观点，都要记录
- 遇到矛盾信息时，记录不同说法及各自来源

## 输出要求
将研究结果保存为结构化文件，包含：
- 每个关键主题的信息摘要（注明信息时间）
- 重要数据和统计数字
- 关键引述和观点（注明来源语言）
- 来源列表（标题 + URL + 发布时间）"""


RESEARCHER_SYSTEM_PROMPT = _build_researcher_system_prompt()


class ResearcherAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="研究员",
            system_prompt=RESEARCHER_SYSTEM_PROMPT,
            model=RESEARCHER_MODEL
        )

    def research(self, workspace: str, plan: dict, round_num: int = 1,
                 additional_queries: list = None) -> str:
        """
        执行研究计划
        round_num: 研究轮次（允许多轮深化研究）
        additional_queries: 额外的搜索查询（来自评审智能体的请求）
        """
        research_dir = os.path.join(workspace, "04_research")
        os.makedirs(research_dir, exist_ok=True)
        output_file = os.path.join(research_dir, f"round_{round_num}.md")
        summary_file = os.path.join(research_dir, "research_summary.md")

        # 构建搜索查询列表
        queries = plan.get("search_queries", [])
        if additional_queries:
            for q in additional_queries:
                queries.append({"query": q, "purpose": "补充研究", "priority": "high", "category": "补充"})

        # 限制每轮的查询数量（第一轮执行所有高/中优先级的，后续轮次执行额外的）
        if round_num == 1:
            exec_queries = [q for q in queries if q.get("priority") in ("high", "medium")][:12]
        else:
            exec_queries = queries[-8:]  # 后续轮次只执行新增的查询

        # 加载已执行查询注册表，过滤掉重复查询
        from tools.verification_registry import load_registry, is_query_executed, add_executed_query, save_registry
        registry = load_registry(workspace)
        executed = set(registry.get("executed_queries", []))

        # 过滤掉已执行的查询
        original_count = len(exec_queries)
        exec_queries = [q for q in exec_queries if q.get("query", "").strip() not in executed]
        skipped = original_count - len(exec_queries)
        if skipped > 0:
            print(f"  [研究员] 跳过 {skipped} 个已执行的查询，执行 {len(exec_queries)} 个新查询", flush=True)

        if not exec_queries:
            print(f"  [研究员] 所有查询均已执行，跳过本轮研究", flush=True)
            return output_file

        skip_note = (f"\n\n注意：{skipped} 个查询在前轮已执行，已跳过，专注于以上 {len(exec_queries)} 个新查询。"
                     if skipped > 0 else "")

        queries_text = json.dumps(exec_queries, ensure_ascii=False, indent=2)

        task = f"""【今天 {_config.CURRENT_DATE_STR}｜优先层：{_config.DATE_3M_AGO_STR} 至今｜补充层：{_config.DATE_6M_AGO_STR} 至 {_config.DATE_3M_AGO_STR}｜超出6个月需标注"历史参考"】

请执行以下研究任务，深入收集关于"{plan.get('question', '该主题')}"的信息。

## 研究目标
{plan.get('objective', '深入研究该主题')}

## 需要执行的搜索查询（第 {round_num} 轮）
{queries_text}

## 执行步骤
1. 对每个搜索查询使用 web_search 工具进行搜索
2. 从搜索结果中选择最有价值的 3-5 个链接，使用 web_fetch 工具获取详细内容
3. 整理所有收集到的信息
4. 将完整研究结果以 Markdown 格式保存到：{output_file}
5. 将研究摘要（最重要的发现）保存到：{summary_file}

## 研究文件格式
```markdown
# 研究结果 - 第{round_num}轮
## 研究问题：{plan.get('question', '')}

## 主要发现
[按主题分类的重要发现]

## 关键数据与统计
[具体数字和数据]

## 重要观点与引述
[专家意见和关键引述]

## 来源列表
[所有参考来源，包含标题和URL]
```

注意：必须实际执行搜索并获取页面内容，不要捏造信息！{skip_note}"""

        result = self.run(task)

        # 将本轮执行的查询注册到注册表
        for q in exec_queries:
            add_executed_query(registry, q.get("query", ""))
        save_registry(workspace, registry)

        return output_file
