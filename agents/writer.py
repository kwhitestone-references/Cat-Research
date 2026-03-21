"""
WriterAgent - 文档撰写智能体
负责将分析结果转化为高质量的研究报告
"""
import os
from agents.base_agent import BaseAgent
from config import WRITER_MODEL
from tools.file_tools import normalize_path


WRITER_SYSTEM_PROMPT = """你是一位专业的研究报告撰写专家，能够将复杂的研究和分析成果转化为清晰、专业、有价值的文档。

## 你的写作原则
1. **准确性**：所有内容必须有研究材料支撑，不凭空添加
2. **深度**：深入分析，提供真正有价值的洞见，不流于表面
3. **清晰性**：结构清晰，逻辑严密，易于理解
4. **完整性**：全面覆盖问题的各个重要方面
5. **专业性**：使用准确的术语，保持专业水准

## 写作风格
- 语言精准、表达流畅
- 段落逻辑清晰，层层递进
- 适当使用小标题、列表等增强可读性
- 数据和事实要具体，避免模糊表述
- 结论要有力，建议要可操作

## 文档结构要求
每份报告必须包含：
1. **标题和摘要** - 核心内容概括
2. **引言/背景** - 问题的重要性和研究背景
3. **主体内容** - 多个维度的深入分析（至少3-5个主要章节）
4. **结论与展望** - 综合结论和未来方向
5. **参考资料** - 主要信息来源

## 改进要求
当收到评审反馈时：
- 认真阅读每条反馈意见
- 逐条解决提出的问题
- 补充缺失的内容
- 改进薄弱的分析
- 提升整体质量"""


class WriterAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="写作者",
            system_prompt=WRITER_SYSTEM_PROMPT,
            model=WRITER_MODEL
        )

    def write_draft(self, workspace: str, question: str, draft_num: int = 0,
                    review_file: str = None) -> str:
        """
        创建或改进报告草稿
        draft_num: 0=初稿，1+=改进版本
        review_file: 评审文件路径（改进时提供）
        """
        analysis_file = os.path.join(workspace, "05_analysis.md")
        research_dir = os.path.join(workspace, "04_research")
        drafts_dir = os.path.join(workspace, "06_drafts")
        os.makedirs(drafts_dir, exist_ok=True)
        output_file = os.path.join(drafts_dir, f"draft_{draft_num}.md")
        final_file = os.path.join(workspace, "09_final.md")

        # 规范化路径（确保正斜杠，Claude 可以正确处理）
        analysis_file = normalize_path(analysis_file)
        research_dir = normalize_path(research_dir)
        output_file = normalize_path(output_file)
        final_file = normalize_path(final_file)

        if draft_num == 0:
            # 创建初稿
            task = f"""请根据分析报告撰写一份全面的研究报告。

## 研究问题
{question}

## 步骤
1. 读取分析报告：{analysis_file}
2. 读取研究资料目录中的文件列表：{research_dir}
3. 必要时读取具体研究文件以获取更多细节
4. 撰写完整的研究报告

## 报告要求
- 字数：不少于3000字（中文）
- 结构完整：必须有标题、摘要、引言、多个分析章节、结论、参考资料
- 内容深度：不只是罗列信息，要有分析和洞见
- 数据具体：使用真实的数字和案例
- 结论有力：提供清晰的结论和可行的建议

## 报告格式（Markdown）
```markdown
# [报告标题]
**摘要：** [100字以内的核心概括]

---

## 引言
[背景介绍，为什么这个问题重要]

## [章节1]
[详细内容...]

## [章节2]
[详细内容...]

...（至少5个主要章节）

## 结论与展望
[综合结论和未来方向]

## 参考资料
[主要来源列表]
```

5. 将报告保存到：{output_file}
6. 同时将报告保存到：{final_file}

请确保报告质量高、内容丰富、分析深入！"""

        else:
            # 基于评审意见改进
            prev_draft = normalize_path(os.path.join(drafts_dir, f"draft_{draft_num - 1}.md"))
            if review_file:
                review_file = normalize_path(review_file)

            task = f"""请根据评审意见改进研究报告，这是第 {draft_num} 次改进。

## 研究问题
{question}

## 步骤
1. 读取上一版草稿：{prev_draft}
2. 读取评审意见：{review_file}
3. 仔细理解每条评审意见
4. 读取分析报告获取补充内容：{analysis_file}
5. 根据反馈全面改进报告

## 改进要求
- **逐条解决**每个评审问题
- **补充**缺失或不足的内容
- **深化**浅显的分析
- **修正**不准确的内容
- **优化**结构和表达
- 在不失去原有优点的同时做出实质性改进
- 改进后的报告应该明显优于上一版

## 输出
将改进后的完整报告保存到：{output_file}
同时更新最终报告：{final_file}

注意：改进必须实质性，不能只是微小调整！"""

        self.run(task)
        return output_file
