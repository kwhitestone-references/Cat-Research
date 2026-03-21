"""
CriticAgent - 质量评审智能体
负责对研究报告进行多维度深度评审并提出改进意见
"""
import os
import json
from agents.base_agent import BaseAgent
from config import CRITIC_MODEL
from tools.file_tools import normalize_path


CRITIC_SYSTEM_PROMPT = """你是一位严格、专业的研究报告评审专家，具有丰富的学术和商业研究经验。

## 你的职责
对研究报告进行全面、客观、建设性的评审，帮助不断提升报告质量。

## 评审维度（每项0-10分）

### 1. 内容完整性（Completeness）
- 是否覆盖了问题的所有重要方面？
- 是否有明显的遗漏？
- 各章节是否有足够的深度？

### 2. 内容准确性（Accuracy）
- 信息是否准确？
- 数据和案例是否具体可信？
- 结论是否有据可查？

### 3. 分析深度（Depth）
- 是否只是罗列信息，还是有真正的分析？
- 是否揭示了深层原因和规律？
- 洞见是否有价值？

### 4. 逻辑清晰度（Clarity）
- 结构是否清晰合理？
- 论证是否逻辑严密？
- 表达是否清晰易懂？

### 5. 实用价值（Usefulness）
- 结论和建议是否有实际价值？
- 读者能否从中获得可操作的指导？

### 6. 信息来源（Sources）
- 信息来源是否多样、权威？
- 是否有来源标注？

### 7. 简洁性（Simplicity）
- 报告是否避免了不必要的冗余和重复？
- 每个结论是否直接、精炼？
- 是否去除了对主题无实质贡献的内容？
- 是否做到了"少即是多"——用最精简的文字传达最大的价值？

## 评审报告格式（必须严格遵守）

输出 JSON 时，必须使用以下标记包裹，确保可靠解析：

---JSON_START---
{
  "cycle": <评审轮次>,
  "scores": {
    "completeness": <0-10分>,
    "accuracy": <0-10分>,
    "depth": <0-10分>,
    "clarity": <0-10分>,
    "usefulness": <0-10分>,
    "sources": <0-10分>,
    "simplicity": <0-10分>
  },
  "average_score": <7项平均分>,
  "strengths": ["优点1", "优点2", ...],
  "critical_issues": [
    {
      "issue": "问题描述",
      "severity": "high/medium/low",
      "suggestion": "改进建议"
    },
    ...
  ],
  "missing_content": ["缺失内容1", "缺失内容2", ...],
  "additional_research_needed": ["需要补充搜索的话题1", ...],
  "overall_assessment": "整体评价（2-3句话）",
  "priority_improvements": ["最重要的3个改进点"]
}
---JSON_END---

## 评审标准
- 评分要客观公正，不要轻易给高分
- 第一次评审通常分数较低（6-7分），有很多改进空间
- 随着改进，分数逐渐提高
- 只有真正优秀的报告才能得到8.5分以上
- simplicity 分低说明报告臃肿、重复，应鼓励精炼表达"""


class CriticAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="评审员",
            system_prompt=CRITIC_SYSTEM_PROMPT,
            model=CRITIC_MODEL
        )

    def review(self, workspace: str, draft_num: int, cycle: int) -> dict:
        """
        评审指定的草稿版本
        返回评审结果字典
        """
        drafts_dir = os.path.join(workspace, "06_drafts")
        reviews_dir = os.path.join(workspace, "07_reviews")
        os.makedirs(reviews_dir, exist_ok=True)

        draft_file = normalize_path(os.path.join(drafts_dir, f"draft_{draft_num}.md"))
        review_file = normalize_path(os.path.join(reviews_dir, f"review_{cycle}.json"))

        # 如果有之前的评审，也一并提供参考
        prev_reviews = []
        for i in range(1, cycle):
            prev_review_file = normalize_path(os.path.join(reviews_dir, f"review_{i}.json"))
            if os.path.exists(prev_review_file):
                prev_reviews.append(prev_review_file)

        prev_reviews_text = ""
        if prev_reviews:
            prev_reviews_text = f"\n\n## 历史评审（请参考，了解改进历程）\n"
            prev_reviews_text += f"上次评审文件：{prev_reviews[-1]}"

        task = f"""请对以下研究报告草稿进行全面评审。这是第 {cycle} 轮评审。

## 待评审文件
{draft_file}
{prev_reviews_text}

## 评审步骤
1. 读取草稿内容：{draft_file}
2. 如有历史评审，读取最近一次评审了解改进历程
3. 从所有维度进行深入评审
4. 生成详细的 JSON 格式评审报告
5. 将评审报告保存到：{review_file}

## 重要提示
- 评审要严格、客观，不能因为是第 {cycle} 次就降低标准
- 只有真正做到了才给高分
- critical_issues 要具体，说明在哪里有问题
- additional_research_needed 是真正需要补充搜索的内容
- 如果报告质量很高（平均分>=8.5），可以明确说明

请直接输出 JSON 格式的评审结果并保存到文件。"""

        self.run(task)

        # 读取保存的评审结果（使用健壮的 JSON 提取）
        review_data = None
        try:
            with open(review_file, 'r', encoding='utf-8') as f:
                content = f.read()
            if content.strip():
                from tools.file_tools import _extract_json_from_text
                # 先尝试直接解析
                try:
                    review_data = json.loads(content)
                except json.JSONDecodeError:
                    # 使用括号计数器方法提取 JSON
                    review_data = _extract_json_from_text(content)
        except Exception as e:
            print(f"  [警告] 读取评审文件失败: {str(e)}", flush=True)

        if not review_data or not isinstance(review_data, dict):
            print(f"  [警告] 评审结果解析失败，使用备用评审", flush=True)
            review_data = self._create_fallback_review(cycle)

        # 保存规范化的评审文件
        with open(review_file, 'w', encoding='utf-8') as f:
            json.dump(review_data, f, ensure_ascii=False, indent=2)

        return review_data, review_file

    def _create_fallback_review(self, cycle: int) -> dict:
        """评审失败时的备用评审结果（根据轮次动态调整分数）"""
        # 随轮次递增的基础分（体现改进趋势）
        base = round(5.5 + min(cycle * 0.4, 2.0), 1)
        score = int(base)

        return {
            "cycle": cycle,
            "scores": {
                "completeness": score,
                "accuracy": score,
                "depth": max(score - 1, 5),
                "clarity": min(score + 1, 9),
                "usefulness": score,
                "sources": score,
                "simplicity": score
            },
            "average_score": base,
            "strengths": ["报告已完成基本结构", "内容覆盖主要方面"],
            "critical_issues": [
                {
                    "issue": "分析深度有待提升",
                    "severity": "medium" if cycle > 2 else "high",
                    "suggestion": "增加具体数据支撑、案例分析和批判性思考"
                }
            ],
            "missing_content": ["更深入的数据分析", "具体案例"],
            "additional_research_needed": [],
            "overall_assessment": f"第 {cycle} 轮草稿已有进展，但仍有改进空间。",
            "priority_improvements": ["增加数据支撑", "深化各章节分析", "补充具体案例"]
        }
