"""
FactCheckerAgent - 事实核查智能体
对分析报告中的关键声明进行交叉验证
"""
import os
import json
import re
from agents.base_agent import BaseAgent
from config import FACT_CHECKER_MODEL
from tools.file_tools import normalize_path
from tools.fact_tools import cross_reference_search


FACT_CHECKER_SYSTEM_PROMPT = """你是一位专业的事实核查专家，擅长识别和验证研究报告中的关键声明、数据点和结论。

## 你的职责
1. 从分析报告中提取所有关键声明和数据点
2. 对每个重要声明进行交叉验证
3. 标记可能不准确或需要进一步验证的内容
4. 提供整体置信度评估

## 识别关键声明的标准
- 包含具体数字、百分比、统计数据的陈述
- 关于趋势、因果关系的结论性陈述
- 关于特定机构、人物、事件的事实性陈述
- 研究结论中的核心论点

## 输出格式（必须严格遵守）
```json
{
  "total_claims_checked": <数量>,
  "claims": [
    {
      "claim": "声明原文",
      "verdict": "supported/disputed/unverifiable/insufficient",
      "confidence": <0.0-1.0>,
      "supporting_count": <支持来源数>,
      "contradicting_count": <反驳来源数>,
      "explanation": "验证说明",
      "needs_attention": true/false
    }
  ],
  "overall_confidence": <0.0-1.0>,
  "high_confidence_claims": <数量>,
  "disputed_claims": <需要关注的声明列表>,
  "unverifiable_claims": <无法验证的声明列表>,
  "fact_check_summary": "整体事实核查结论",
  "recommended_additions": ["建议补充的内容或数据"]
}
```"""


class FactCheckerAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="事实核查员",
            system_prompt=FACT_CHECKER_SYSTEM_PROMPT,
            model=FACT_CHECKER_MODEL
        )

    def check_facts(self, workspace: str, analysis_file: str = None,
                    registry: dict = None, cycle: int = 0) -> tuple:
        """
        对分析报告中的关键声明进行事实核查
        """
        analysis_dir = normalize_path(os.path.join(workspace, ""))
        verification_dir = normalize_path(os.path.join(workspace, "08_verification"))
        os.makedirs(verification_dir.replace('/', os.sep), exist_ok=True)

        output_file = normalize_path(os.path.join(verification_dir, "fact_check.json"))

        # 如果没有指定分析文件，使用固定路径
        if not analysis_file:
            candidate = os.path.join(workspace, "05_analysis.md").replace('/', os.sep)
            analysis_file = candidate if os.path.exists(candidate) else None

        # 预提取关键声明并进行交叉验证
        pre_check_results = self._precheck_claims(analysis_file, registry=registry, cycle=cycle)

        # 统计缓存命中与新核查数量
        cached_count = sum(1 for r in pre_check_results if r.get("_from_cache"))
        new_count = len(pre_check_results) - cached_count
        cache_note = (f"\n## 已完成核查（直接复用，无需重复）\n"
                      f"已从注册表复用 {cached_count} 个声明的核查结果，"
                      f"仅对 {new_count} 个新声明执行核查。\n") if cached_count > 0 else ""

        task = f"""请对研究分析报告中的关键声明进行系统性事实核查。
{cache_note}
## 待核查的分析文件
{normalize_path(analysis_file) if analysis_file else analysis_dir + " 目录下最新的分析文件"}

## 预核查结果（已自动验证的声明）
{json.dumps(pre_check_results, ensure_ascii=False, indent=2) if pre_check_results else "无预核查结果"}

## 核查步骤
1. 读取分析文件，提取所有关键声明（特别是包含数据、统计、趋势判断的陈述）
2. 优先核查以下类型的声明：
   - 具体数字和百分比（如"市场规模达XXX亿"）
   - 趋势判断（如"增长了X%"）
   - 因果关系声明（如"由于A导致了B"）
   - 关于特定组织/机构的事实陈述
3. 结合预核查结果，综合评估每个声明的可信度
4. 特别标注有争议或无法验证的声明
5. 生成 JSON 格式核查报告并保存到：{output_file}

## 重要提示
- 声明核查应基于预核查结果和分析文件中引用的来源
- 对于无法通过网络验证的声明，标注为 "unverifiable"
- overall_confidence 应反映整体报告可信度
- disputed_claims 和 unverifiable_claims 只保留声明的简短文本

请直接生成并保存核查报告。"""

        self.run(task)

        # 读取核查结果
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
            print(f"  [警告] 读取事实核查结果失败: {str(e)}", flush=True)

        if not result or not isinstance(result, dict):
            result = self._create_fallback_result(pre_check_results)
            with open(output_file.replace('/', os.sep), 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

        return result, output_file

    def _precheck_claims(self, analysis_file: str, registry: dict = None, cycle: int = 0) -> list:
        """从分析文件中预提取关键声明并进行快速验证，跳过已验证声明"""
        if not analysis_file:
            return []

        fpath = analysis_file.replace('/', os.sep)
        if not os.path.exists(fpath):
            return []

        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            return []

        # 提取包含数字的关键句子作为声明
        sentences = re.split(r'[。\n]', content)
        claims = []
        for sent in sentences:
            sent = sent.strip()
            if (re.search(r'\d+', sent) or
                any(kw in sent for kw in ['增长', '下降', '提升', '降低', '达到', '超过', '占比'])):
                if 20 <= len(sent) <= 200:
                    claims.append(sent)

        # 加载注册表中已验证的声明
        from tools.verification_registry import is_claim_verified, get_claim_result, add_claim_result
        results = []
        new_claims_to_check = []

        for claim in claims[:6]:  # 最多取6个候选
            if registry and is_claim_verified(registry, claim):
                # 直接复用已验证结果
                cached = get_claim_result(registry, claim)
                results.append({
                    "claim": claim[:100],
                    "verdict": cached.get("verdict", "supported"),
                    "confidence": cached.get("confidence", 0.8),
                    "supporting_count": cached.get("supporting_count", 1),
                    "contradicting_count": cached.get("contradicting_count", 0),
                    "_from_cache": True
                })
            else:
                new_claims_to_check.append(claim)

        # 只对新声明调用 API（最多3个）
        for claim in new_claims_to_check[:3]:
            try:
                check_result = json.loads(cross_reference_search(claim, max_queries=2))
                r = {
                    "claim": claim[:100],
                    "verdict": check_result.get("verdict", "insufficient"),
                    "confidence": check_result.get("confidence", 0.3),
                    "supporting_count": len(check_result.get("supporting", [])),
                    "contradicting_count": len(check_result.get("contradicting", []))
                }
                results.append(r)
                if registry is not None:
                    add_claim_result(registry, claim, r, cycle=cycle)
            except Exception:
                continue

        return results

    def _create_fallback_result(self, pre_check_results: list) -> dict:
        """创建备用核查结果"""
        if not pre_check_results:
            return {
                "total_claims_checked": 0,
                "claims": [],
                "overall_confidence": 0.6,
                "high_confidence_claims": 0,
                "disputed_claims": [],
                "unverifiable_claims": [],
                "fact_check_summary": "事实核查工具未能完成完整核查，建议人工审核关键数据点。",
                "recommended_additions": ["建议补充权威来源引用", "建议添加数据来源说明"]
            }

        supported = [r for r in pre_check_results if r.get('verdict') == 'supported']
        disputed = [r['claim'][:50] for r in pre_check_results if r.get('verdict') == 'disputed']
        unverifiable = [r['claim'][:50] for r in pre_check_results if r.get('verdict') in ('unverifiable', 'insufficient')]

        overall_conf = sum(r.get('confidence', 0.5) for r in pre_check_results) / max(len(pre_check_results), 1)

        return {
            "total_claims_checked": len(pre_check_results),
            "claims": pre_check_results,
            "overall_confidence": round(overall_conf, 2),
            "high_confidence_claims": len(supported),
            "disputed_claims": disputed,
            "unverifiable_claims": unverifiable,
            "fact_check_summary": f"已核查 {len(pre_check_results)} 个关键声明，{len(supported)} 个得到验证，{len(disputed)} 个存在争议。",
            "recommended_additions": ["建议为所有数据添加具体来源引用"]
        }
