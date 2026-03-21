"""
SourceVerifierAgent - 来源可信度验证智能体
对研究收集的所有来源进行多维度可信度评估
"""
import os
import json
from agents.base_agent import BaseAgent
from config import SOURCE_VERIFIER_MODEL
from tools.file_tools import normalize_path
from tools.domain_checker import assess_source_list


SOURCE_VERIFIER_SYSTEM_PROMPT = """你是一位专业的信息来源可信度评估专家，专注于判断信息来源的权威性、准确性和可靠性。

## 你的职责
对研究数据中的所有来源进行系统性评估，生成详细的可信度报告，帮助确保最终研究结论基于高质量来源。

## 评估维度
1. **域名权威性** - 来源网站是否是公认的权威机构
2. **内容相关性** - 来源内容与研究问题的相关程度
3. **信息时效性** - 来源信息是否足够新鲜
4. **多源验证** - 重要结论是否有多个来源交叉印证

## 输出格式（必须严格遵守）
```json
{
  "total_sources": <总来源数>,
  "verified_sources": [
    {
      "url": "来源URL",
      "title": "来源标题",
      "domain_score": <0-100>,
      "confidence_level": "high/medium/low/unknown",
      "tier": <1/2/3/4>,
      "category": "academic/government/news/research/general",
      "is_reliable": true/false,
      "warning": "如有问题请说明，否则为空字符串"
    }
  ],
  "summary": {
    "high_confidence_count": <数量>,
    "medium_confidence_count": <数量>,
    "low_confidence_count": <数量>,
    "average_score": <平均分>,
    "overall_quality": "excellent/good/fair/poor",
    "recommendation": "整体来源质量评价和建议"
  },
  "unreliable_sources": ["需要替换或谨慎引用的来源URL列表"],
  "top_sources": ["最可靠的5个来源URL列表"]
}
```"""


class SourceVerifierAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="来源验证员",
            system_prompt=SOURCE_VERIFIER_SYSTEM_PROMPT,
            model=SOURCE_VERIFIER_MODEL
        )

    def verify_sources(self, workspace: str) -> dict:
        """
        验证工作空间中的所有研究来源
        返回验证结果字典
        """
        research_dir = normalize_path(os.path.join(workspace, "04_research"))
        verification_dir = normalize_path(os.path.join(workspace, "08_verification"))
        os.makedirs(verification_dir.replace('/', os.sep), exist_ok=True)

        output_file = normalize_path(os.path.join(verification_dir, "source_verification.json"))

        # 先用 domain_checker 对研究文件中的来源做预处理
        sources = self._collect_sources_from_research(research_dir)
        pre_assessment = {}
        if sources:
            pre_assessment = assess_source_list(sources)

        task = f"""请对以下研究数据中的所有信息来源进行可信度验证。

## 研究数据目录
{research_dir}

## 预处理评估结果（供参考）
已自动对 {len(sources)} 个来源进行了初步域名权威性评估。
平均得分：{pre_assessment.get('summary', {}).get('average_score', 'N/A')}
整体质量：{pre_assessment.get('summary', {}).get('overall_quality', 'N/A')}
高可信来源数：{pre_assessment.get('summary', {}).get('high_confidence', 0)}
中等可信来源数：{pre_assessment.get('summary', {}).get('medium_confidence', 0)}
低可信来源数：{pre_assessment.get('summary', {}).get('low_confidence', 0)}

## 验证步骤
1. 读取 {research_dir} 目录下的所有研究文件（research_*.md 文件）
2. 从每个文件中提取所有引用的 URL 和来源信息
3. 结合预处理评估结果，对每个来源进行综合评估
4. 特别关注：
   - 来源是否来自权威机构（政府、学术、主流媒体）
   - 来源是否与研究主题直接相关
   - 是否有多个独立来源印证同一信息
5. 生成完整的 JSON 格式验证报告
6. 将报告保存到：{output_file}

## 重要提示
- 对 Tier 4（未知域名）来源需特别说明
- 标记所有可疑或低可信度来源
- 推荐研究员应优先引用的高质量来源
- 严格按照系统提示中的 JSON 格式输出

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
            print(f"  [警告] 读取来源验证结果失败: {str(e)}", flush=True)

        if not result or not isinstance(result, dict):
            # 使用预处理结果作为备用
            result = self._create_fallback_result(pre_assessment, sources)
            with open(output_file.replace('/', os.sep), 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

        return result, output_file

    def _collect_sources_from_research(self, research_dir: str) -> list:
        """从研究文件中提取 URL 来源"""
        import re
        sources = []
        seen_urls = set()
        research_path = research_dir.replace('/', os.sep)

        if not os.path.exists(research_path):
            return sources

        for fname in os.listdir(research_path):
            if not fname.endswith('.md'):
                continue
            fpath = os.path.join(research_path, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                # 提取 URL
                urls = re.findall(r'https?://[^\s\)\]\"\'>]+', content)
                for url in urls:
                    url = url.rstrip('.,;:)')
                    if url not in seen_urls:
                        seen_urls.add(url)
                        # 尝试从上下文提取标题
                        idx = content.find(url)
                        surrounding = content[max(0, idx-100):idx+100]
                        title_match = re.search(r'\[([^\]]+)\]', surrounding)
                        title = title_match.group(1) if title_match else url.split('/')[2]
                        sources.append({"url": url, "title": title})
            except Exception:
                continue

        return sources

    def _create_fallback_result(self, pre_assessment: dict, sources: list) -> dict:
        """创建备用验证结果"""
        summary_data = pre_assessment.get('summary', {})
        assessed = pre_assessment.get('sources', [])

        verified_sources = []
        unreliable = []
        top_sources = []

        for src in assessed:
            entry = {
                "url": src.get('url', ''),
                "title": src.get('title', ''),
                "domain_score": src.get('final_score', 40),
                "confidence_level": src.get('confidence_level', 'unknown'),
                "tier": src.get('tier', 4),
                "category": src.get('category', 'general'),
                "is_reliable": src.get('final_score', 0) >= 60,
                "warning": ', '.join(src.get('flags', [])) if src.get('flags') else ''
            }
            verified_sources.append(entry)
            if src.get('final_score', 0) < 50:
                unreliable.append(src.get('url', ''))
            elif src.get('final_score', 0) >= 75:
                top_sources.append(src.get('url', ''))

        return {
            "total_sources": len(sources),
            "verified_sources": verified_sources[:20],
            "summary": {
                "high_confidence_count": summary_data.get('high_confidence', 0),
                "medium_confidence_count": summary_data.get('medium_confidence', 0),
                "low_confidence_count": summary_data.get('low_confidence', 0),
                "average_score": summary_data.get('average_score', 50),
                "overall_quality": summary_data.get('overall_quality', 'fair'),
                "recommendation": "建议研究员优先引用高可信度来源，对低可信度来源进行核实后再引用。"
            },
            "unreliable_sources": unreliable[:10],
            "top_sources": top_sources[:5]
        }
