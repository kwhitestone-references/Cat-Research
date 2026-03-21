"""
ConclusionValidatorAgent - 结论验证智能体
对研究报告的结论进行全面性和准确性验证
"""
import os
import json
from agents.base_agent import BaseAgent
from config import CONCLUSION_VALIDATOR_MODEL
from tools.file_tools import normalize_path


CONCLUSION_VALIDATOR_SYSTEM_PROMPT = """你是一位严格的研究结论验证专家，专注于确保研究结论的逻辑严密性、全面性和准确性。

## 你的职责
1. 验证结论是否有充分的证据支撑
2. 检查结论覆盖的广度是否足够
3. 识别结论中可能存在的逻辑漏洞
4. 评估结论对原始问题的回答是否完整
5. 提出针对性的改进建议

## 验证维度（每项0-10分）
- **证据充分性**：结论是否有足够的事实和数据支撑
- **逻辑严密性**：推理过程是否严密，无明显跳跃
- **覆盖全面性**：是否覆盖了问题的各个重要方面
- **实用价值**：结论是否具有实际指导意义
- **局限性说明**：是否合理说明了研究局限

## 输出格式（必须严格遵守）
```json
{
  "validation_scores": {
    "evidence_sufficiency": <0-10>,
    "logical_rigor": <0-10>,
    "coverage_completeness": <0-10>,
    "practical_value": <0-10>,
    "limitations_acknowledged": <0-10>
  },
  "average_score": <平均分>,
  "conclusion_confidence": <0.0-1.0>,
  "strengths": ["结论的优点1", "优点2"],
  "gaps": [
    {
      "gap": "缺口描述",
      "importance": "high/medium/low",
      "suggestion": "填补建议"
    }
  ],
  "logic_issues": ["逻辑问题1（如有）"],
  "missing_perspectives": ["未覆盖的重要视角"],
  "overall_verdict": "pass/needs_improvement/fail",
  "improvement_instructions": "给写作智能体的具体改进指令（3-5条）",
  "confidence_breakdown": {
    "source_quality_weight": 0.25,
    "fact_accuracy_weight": 0.35,
    "conclusion_validity_weight": 0.40,
    "final_confidence": <0.0-1.0>
  }
}
```"""


class ConclusionValidatorAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="结论验证员",
            system_prompt=CONCLUSION_VALIDATOR_SYSTEM_PROMPT,
            model=CONCLUSION_VALIDATOR_MODEL
        )

    def validate_conclusions(self, workspace: str, draft_file: str = None,
                             source_verification: dict = None,
                             fact_check: dict = None,
                             registry: dict = None,
                             cycle: int = 1) -> tuple:
        """
        验证研究报告的结论质量
        """
        drafts_dir = normalize_path(os.path.join(workspace, "06_drafts"))
        verification_dir = normalize_path(os.path.join(workspace, "08_verification"))
        plan_dir = normalize_path(os.path.join(workspace, "02_plan"))
        os.makedirs(verification_dir.replace('/', os.sep), exist_ok=True)

        output_file = normalize_path(os.path.join(verification_dir, "conclusion_validation.json"))

        # 找到最新草稿
        if not draft_file:
            draft_file = self._find_latest_draft(drafts_dir.replace('/', os.sep))

        # 计算综合置信度
        source_score = self._extract_source_score(source_verification)
        fact_confidence = self._extract_fact_confidence(fact_check)

        # 从注册表获取已验证来源和声明的概要（避免重复读取）
        verified_src_count = len(registry.get("verified_sources", {})) if registry else 0
        verified_claim_count = len(registry.get("verified_claims", {})) if registry else 0
        registry_summary = (
            f"\n## 已验证信息（注册表，直接使用，无需重新核查）\n"
            f"- 已验证来源：{verified_src_count} 个\n"
            f"- 已验证声明：{verified_claim_count} 个\n"
        ) if (verified_src_count or verified_claim_count) else ""

        task = f"""请对研究报告的结论进行全面验证。
{registry_summary}

## 待验证的草稿
{normalize_path(draft_file) if draft_file else drafts_dir + " 目录下最新草稿"}

## 研究计划（了解原始问题）
{plan_dir}/research_plan.md（如存在）

## 来源可信度评估摘要
- 来源平均得分：{source_score:.1f}/100
- 高可信来源占比：{source_verification.get('summary', {}).get('high_confidence_count', 'N/A')} 个高可信来源

## 事实核查摘要
- 整体置信度：{fact_confidence:.0%}
- 已核查声明数：{fact_check.get('total_claims_checked', 0) if fact_check else 0}
- 争议声明：{fact_check.get('disputed_claims', [])[:3] if fact_check else []}

## 验证步骤
1. 读取研究草稿，重点关注结论章节（通常在末尾）
2. 读取研究计划（如存在），确认结论是否完整回答了原始问题
3. 对照来源质量和事实核查结果，评估结论可信度
4. 从以下5个维度打分并识别问题：
   - 证据充分性：每个结论是否有数据/案例支撑？
   - 逻辑严密性：结论是否从证据中合理推导？
   - 覆盖全面性：是否遗漏了重要方面？
   - 实用价值：建议是否可操作？
   - 局限性说明：是否诚实说明了研究限制？
5. 计算综合置信度（来源质量25% + 事实核查35% + 结论有效性40%）
6. 生成改进指令（针对写作智能体的具体、可执行的修改建议）
7. 将验证报告保存到：{output_file}

## 重要提示
- overall_verdict 为 "pass" 表示结论质量达标，"needs_improvement" 表示需要改进，"fail" 表示需要重写
- improvement_instructions 必须具体、可操作，帮助写作智能体快速改进
- 平均分 >= 7.5 可考虑 "pass"，6-7.5 为 "needs_improvement"，< 6 为 "fail"

请直接生成并保存验证报告。"""

        self.run(task)

        # 读取验证结果
        result = None
        try:
            output_path = output_file.replace('/', os.sep)
            if os.path.exists(output_path):
                with open(output_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                if content.strip():
                    from tools.file_tools import _extract_json_from_text
                    try:
                        result = json.loads(content)
                    except json.JSONDecodeError:
                        result = _extract_json_from_text(content)
        except Exception as e:
            print(f"  [警告] 读取结论验证结果失败: {str(e)}", flush=True)

        if not result or not isinstance(result, dict):
            result = self._create_fallback_result(source_score, fact_confidence)
            with open(output_file.replace('/', os.sep), 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

        return result, output_file

    def _find_latest_draft(self, drafts_dir: str) -> str:
        """找到最新的草稿文件"""
        drafts_path = drafts_dir.replace('/', os.sep)
        if not os.path.exists(drafts_path):
            return None
        files = [f for f in os.listdir(drafts_path) if f.startswith('draft_') and f.endswith('.md')]
        if not files:
            return None
        files.sort(key=lambda x: int(x.split('_')[1].split('.')[0]) if x.split('_')[1].split('.')[0].isdigit() else 0, reverse=True)
        return os.path.join(drafts_path, files[0])

    def _extract_source_score(self, source_verification: dict) -> float:
        if not source_verification:
            return 60.0
        summary = source_verification.get('summary', {})
        return float(summary.get('average_score', 60.0))

    def _extract_fact_confidence(self, fact_check: dict) -> float:
        if not fact_check:
            return 0.6
        return float(fact_check.get('overall_confidence', 0.6))

    def _create_fallback_result(self, source_score: float, fact_confidence: float) -> dict:
        """创建备用验证结果"""
        # 综合置信度计算
        conclusion_validity = 0.65  # 默认结论有效性
        final_confidence = (source_score / 100 * 0.25 + fact_confidence * 0.35 + conclusion_validity * 0.40)

        return {
            "validation_scores": {
                "evidence_sufficiency": 7,
                "logical_rigor": 7,
                "coverage_completeness": 6,
                "practical_value": 7,
                "limitations_acknowledged": 6
            },
            "average_score": 6.6,
            "conclusion_confidence": round(final_confidence, 2),
            "strengths": ["报告结构完整", "数据引用较为充分"],
            "gaps": [
                {
                    "gap": "部分结论缺乏足够的数据支撑",
                    "importance": "medium",
                    "suggestion": "为每个主要结论添加至少2个数据来源"
                }
            ],
            "logic_issues": [],
            "missing_perspectives": ["长期趋势分析", "反例和挑战"],
            "overall_verdict": "needs_improvement",
            "improvement_instructions": "1. 为每个主要结论补充具体数据支持\n2. 增加与研究问题直接相关的可操作建议\n3. 添加研究局限性说明\n4. 确保结论完整回答了研究问题的每个子方面",
            "confidence_breakdown": {
                "source_quality_weight": 0.25,
                "fact_accuracy_weight": 0.35,
                "conclusion_validity_weight": 0.40,
                "final_confidence": round(final_confidence, 2)
            }
        }
