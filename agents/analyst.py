"""
AnalystAgent - 分析综合智能体
负责对研究结果进行深入分析和综合
"""
import os
from agents.base_agent import BaseAgent
from config import ANALYST_MODEL


ANALYST_SYSTEM_PROMPT = """你是一位专业的研究分析师，擅长从大量信息中提炼洞见、发现规律、建立联系。

## 你的职责
1. 读取和理解所有研究材料
2. 进行深入的分析和综合
3. 识别关键模式、趋势和洞见
4. 建立信息之间的逻辑联系
5. 产生有价值的分析结论

## 分析框架
- **事实提炼**：从信息中提取核心事实，去除重复和噪音
- **规律识别**：发现数据和案例中的规律
- **因果分析**：分析现象的原因和影响
- **对比分析**：比较不同观点、数据、案例
- **趋势推断**：基于现有数据推断发展方向
- **风险评估**：识别潜在的问题和挑战

## 分析质量要求
- 分析结论必须有据可查，来自研究材料
- 区分已确认的事实和推断性观点
- 保持客观中立，呈现多角度视角
- 对复杂问题提供有深度的解读

## 输出格式
产出结构清晰的分析报告，包含：
- 执行摘要（最重要的3-5个结论）
- 分主题的详细分析
- 数据洞见
- 综合结论"""


class AnalystAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="分析师",
            system_prompt=ANALYST_SYSTEM_PROMPT,
            model=ANALYST_MODEL
        )

    def analyze(self, workspace: str, question: str) -> str:
        """
        对研究结果进行分析综合
        """
        research_dir = os.path.join(workspace, "04_research")
        output_file = os.path.join(workspace, "05_analysis.md")

        task = f"""请对以下工作空间中的研究材料进行深入分析。

## 研究问题
{question}

## 步骤
1. 列出研究目录中的所有文件：{research_dir}
2. 读取所有研究文件的内容
3. 进行全面的分析和综合
4. 将分析结果保存到：{output_file}

## 分析报告格式
```markdown
# 研究分析报告

## 执行摘要
[3-5个最重要的核心结论，每个1-2句话]

## 一、主要发现与关键事实
[基于研究材料的核心发现，要有具体数据]

## 二、深度分析
### 2.1 [分析维度1]
### 2.2 [分析维度2]
### 2.3 [分析维度3]
...

## 三、多角度视角
[不同立场、观点的对比分析]

## 四、数据洞见
[关键数据的解读和含义]

## 五、综合结论
[综合所有分析得出的结论]

## 六、研究局限性
[信息来源的限制、可能的偏差等]
```

请确保分析深入、有理有据、洞见独到！"""

        self.run(task)
        return output_file
