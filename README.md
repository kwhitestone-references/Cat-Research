<div align="center">

# 🐱 Cat-Agent · 多智能体深度研究系统

**让 AI 像专业研究员一样思考、验证、迭代**

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![OpenAI Compatible](https://img.shields.io/badge/API-OpenAI%20Compatible-412991?style=flat-square&logo=openai&logoColor=white)](https://platform.openai.com)

[中文](#-中文文档) · [English](#-english-documentation)

</div>

---

## 📖 中文文档

### 项目简介

Cat-Agent 是一个**多智能体协作深度研究系统**，将一个研究问题分解为 8 个专业阶段，由 8 个不同职责的 AI 智能体协同完成，最终输出经过来源验证、事实核查、结论验证的高质量研究报告。

不同于普通的 AI 问答，Cat-Agent 会：
- 🔍 **主动搜索**最新网络信息（时效优先）
- 🔗 **验证来源**权威性（7 级评分体系）
- ✅ **核查事实**（交叉验证关键声明）
- 🔄 **迭代改进**（最少 2-5 轮质量循环）
- 📊 **输出置信度报告**（综合质量评分）

---

### 系统架构

```
用户提问
   │
   ▼
┌─────────────────────────────────────────────────────┐
│                   Orchestrator                      │
│                  （研究协调器）                      │
└─────────────────────────────────────────────────────┘
   │
   ├─→ [阶段1] 🗣️  Clarifier          意图识别与问题澄清
   │
   ├─→ [阶段2] 📋  Planner            研究规划（10-16个搜索查询）
   │
   ├─→ [阶段3] 🔍  Researcher         网络搜索 + 网页抓取
   │
   ├─→ [阶段3.5] 🔎 SourceVerifier   来源权威性验证
   │
   ├─→ [阶段4] 🧐  Analyst            综合分析
   │
   ├─→ [阶段5] ✍️  Writer             初稿撰写
   │
   ├─→ [阶段5.5] 🔬 FactChecker      事实核查
   │
   └─→ [阶段6] 🔄  质量改进循环（≥2-5轮）
           ├─→ Critic              多维度评审（7项评分）
           ├─→ Researcher          补充研究（前3轮）
           ├─→ ConclusionValidator  结论验证（5项评分）
           └─→ Writer              迭代改进
   │
   ▼
最终研究报告 + 置信度报告
```

---

### 8 大智能体

| 智能体 | 职责 |
|--------|------|
| 🗣️ **Clarifier**（澄清者） | 识别用户意图，澄清研究方向，动态调整研究策略 |
| 📋 **Planner**（规划师） | 分解问题，设计 10-16 个多语言搜索查询，按时效分层 |
| 🔍 **Researcher**（研究员） | 执行网络搜索，抓取网页，多源收集信息 |
| 🧐 **Analyst**（分析师） | 综合研究材料，提炼关键发现，进行因果/趋势分析 |
| ✍️ **Writer**（写作者） | 撰写专业研究报告，根据反馈迭代改进 |
| 🎯 **Critic**（评审员） | 7 维度评审报告（完整性/准确性/深度/清晰性等） |
| 🔎 **SourceVerifier**（来源验证员） | 评估信息来源权威性，分 Tier 1-4 级别标注 |
| 🔬 **FactChecker**（事实核查员） | 交叉验证关键声明，计算置信度（0.0-1.0） |
| ✔️ **ConclusionValidator**（结论验证员） | 验证结论逻辑严密性、全面性和实用价值 |

---

### 快速开始

#### 1. 克隆项目

```bash
git clone https://github.com/mmlong818/cat-agent.git
cd cat-agent
```

#### 2. 安装依赖

```bash
pip install -r requirements.txt
```

#### 3. 配置 API Key

```bash
# 复制配置模板
cp .env.example .env
cp settings.example.json settings.json

# 编辑 .env，填入你的 API Key
# 支持：智谱 GLM / OpenAI / 任意 OpenAI 兼容服务
```

`.env` 内容示例：
```env
ZHIPU_API_KEY=your_api_key_here
```

`settings.json` 内容示例：
```json
{
  "api_key": "your_api_key_here",
  "base_url": "https://open.bigmodel.cn/api/paas/v4/",
  "core_model": "glm-4.7",
  "support_model": "glm-4.7-flash"
}
```

#### 4. 启动方式

**方式一：命令行**
```bash
# 直接提问
python main.py "2024年大模型行业有哪些重要进展？"

# 交互模式
python main.py
```

**方式二：Web UI + API 服务**
```bash
python run_api.py
# 访问 http://localhost:8000
```

![Web UI 截图占位](docs/screenshot.png)

---

### 输出结构

每次研究会在 `workspace/` 目录生成独立会话文件夹：

```
workspace/session_20240318_143022/
├── 01_question.txt              # 原始问题
├── 02_clarification.txt         # 澄清结果
├── 03_plan.json                 # 研究计划
├── 04_research/                 # 原始搜索数据
├── 05_analysis.md               # 综合分析
├── 06_drafts/                   # 历次草稿
├── 07_reviews/                  # 评审记录（含分数）
├── 08_verification/             # 验证结果
│   ├── source_verification.json
│   ├── fact_check_cycle_0.json
│   └── conclusion_validation_cycle_N.json
├── 09_final.md                  # 📄 最终研究报告
└── 10_confidence_report.json    # 📊 置信度报告
```

---

### API 端点

启动 `python run_api.py` 后可访问：

| 方法 | 端点 | 说明 |
|------|------|------|
| `GET` | `/` | Web UI |
| `GET` | `/docs` | Swagger API 文档 |
| `POST` | `/api/clarify/start` | 开始澄清对话 |
| `POST` | `/api/clarify/message` | 发送澄清消息 |
| `POST` | `/api/clarify/confirm` | 确认并开始研究 |
| `POST` | `/api/research/start` | 启动研究（SSE 流式返回） |
| `GET` | `/api/research/status/{id}` | 查询任务状态 |
| `POST` | `/api/research/stop/{id}` | 停止任务 |
| `GET` | `/api/sessions` | 获取历史会话列表 |
| `GET` | `/api/config` | 获取当前配置 |
| `POST` | `/api/settings` | 更新 API 配置 |

---

### 配置说明

所有配置均可通过环境变量覆盖：

```env
# 模型配置
CORE_MODEL=glm-4.7           # 核心模型（规划/研究/分析/写作）
SUPPORT_MODEL=glm-4.7-flash  # 辅助模型（评审/验证）

# 研究质量参数
MAX_IMPROVEMENT_CYCLES=5     # 最多改进轮数
MIN_IMPROVEMENT_CYCLES=2     # 最少强制改进轮数
QUALITY_THRESHOLD=8.0        # 质量阈值（满分10）

# API 服务
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:8000
```

---

### 系统要求

- Python 3.9+
- API Key（智谱 GLM / OpenAI / 其他兼容服务）
- 正常网络连接（用于网络搜索）
- 内存：512MB+（推荐 2GB）

---

## 📖 English Documentation

### Overview

**Cat-Agent** is a multi-agent collaborative deep research system. It decomposes a research question into 8 specialized stages, processed by 8 AI agents with distinct roles, ultimately delivering a high-quality research report with source verification, fact-checking, and conclusion validation.

Unlike simple AI Q&A tools, Cat-Agent will:
- 🔍 **Actively search** for the latest web information (recency-first)
- 🔗 **Verify sources** with a 7-tier authority scoring system
- ✅ **Fact-check** claims through cross-reference validation
- 🔄 **Iteratively improve** with a minimum of 2–5 quality cycles
- 📊 **Output a confidence report** with comprehensive quality scoring

---

### Architecture

```
User Query
   │
   ▼
┌─────────────────────────────────────────────────────┐
│                    Orchestrator                     │
└─────────────────────────────────────────────────────┘
   │
   ├─→ [Stage 1] 🗣️  Clarifier          Intent recognition & clarification
   │
   ├─→ [Stage 2] 📋  Planner            Research planning (10–16 queries)
   │
   ├─→ [Stage 3] 🔍  Researcher         Web search + page scraping
   │
   ├─→ [Stage 3.5] 🔎 SourceVerifier   Source authority verification
   │
   ├─→ [Stage 4] 🧐  Analyst            Synthesis & analysis
   │
   ├─→ [Stage 5] ✍️  Writer             First draft
   │
   ├─→ [Stage 5.5] 🔬 FactChecker      Fact verification
   │
   └─→ [Stage 6] 🔄  Quality Loop (≥ 2–5 rounds)
           ├─→ Critic              Multi-dimension review (7 scores)
           ├─→ Researcher          Supplemental research (first 3 rounds)
           ├─→ ConclusionValidator  Conclusion validation (5 scores)
           └─→ Writer              Iterative improvement
   │
   ▼
Final Report + Confidence Report
```

---

### 8 Specialized Agents

| Agent | Role |
|-------|------|
| 🗣️ **Clarifier** | Identifies user intent, clarifies research scope, dynamically adjusts strategy |
| 📋 **Planner** | Breaks down the question into 10–16 multilingual queries, layered by recency |
| 🔍 **Researcher** | Executes web searches, scrapes pages, aggregates multi-source data |
| 🧐 **Analyst** | Synthesizes research, extracts key findings, performs causal/trend analysis |
| ✍️ **Writer** | Writes professional research reports and iterates based on feedback |
| 🎯 **Critic** | Reviews on 7 dimensions: completeness, accuracy, depth, clarity, etc. |
| 🔎 **SourceVerifier** | Scores source authority and labels Tier 1–4 credibility levels |
| 🔬 **FactChecker** | Cross-validates key claims, assigns confidence scores (0.0–1.0) |
| ✔️ **ConclusionValidator** | Validates logical rigor, completeness, and practical value of conclusions |

---

### Quick Start

#### 1. Clone

```bash
git clone https://github.com/mmlong818/cat-agent.git
cd cat-agent
```

#### 2. Install dependencies

```bash
pip install -r requirements.txt
```

#### 3. Configure API Key

```bash
cp .env.example .env
cp settings.example.json settings.json
# Edit .env and fill in your API key
```

`.env` example:
```env
ZHIPU_API_KEY=your_api_key_here
```

`settings.json` example:
```json
{
  "api_key": "your_api_key_here",
  "base_url": "https://open.bigmodel.cn/api/paas/v4/",
  "core_model": "glm-4.7",
  "support_model": "glm-4.7-flash"
}
```

#### 4. Run

**CLI mode:**
```bash
python main.py "What are the major AI trends in 2024?"
# or interactive mode:
python main.py
```

**Web UI + API server:**
```bash
python run_api.py
# Open http://localhost:8000
```

---

### Output Structure

Each research session creates an isolated folder under `workspace/`:

```
workspace/session_20240318_143022/
├── 01_question.txt              # Original question
├── 02_clarification.txt         # Clarification result
├── 03_plan.json                 # Research plan
├── 04_research/                 # Raw search data
├── 05_analysis.md               # Synthesized analysis
├── 06_drafts/                   # Draft history
├── 07_reviews/                  # Review records (with scores)
├── 08_verification/             # Verification results
│   ├── source_verification.json
│   ├── fact_check_cycle_0.json
│   └── conclusion_validation_cycle_N.json
├── 09_final.md                  # 📄 Final research report
└── 10_confidence_report.json    # 📊 Confidence report
```

---

### API Reference

After running `python run_api.py`:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Web UI |
| `GET` | `/docs` | Swagger API docs |
| `POST` | `/api/clarify/start` | Start clarification dialog |
| `POST` | `/api/clarify/message` | Send clarification message |
| `POST` | `/api/clarify/confirm` | Confirm and begin research |
| `POST` | `/api/research/start` | Start research (SSE streaming) |
| `GET` | `/api/research/status/{id}` | Query task status |
| `POST` | `/api/research/stop/{id}` | Stop a task |
| `GET` | `/api/sessions` | List research history |
| `GET` | `/api/config` | Get current configuration |
| `POST` | `/api/settings` | Update API settings |

---

### Configuration

All settings can be overridden via environment variables:

```env
# Model selection
CORE_MODEL=glm-4.7           # Core model (planning / research / writing)
SUPPORT_MODEL=glm-4.7-flash  # Support model (review / validation)

# Quality parameters
MAX_IMPROVEMENT_CYCLES=5     # Maximum improvement rounds
MIN_IMPROVEMENT_CYCLES=2     # Minimum forced improvement rounds
QUALITY_THRESHOLD=8.0        # Quality threshold (out of 10)

# API server
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:8000
```

---

### Requirements

- Python 3.9+
- API Key (Zhipu GLM / OpenAI / any OpenAI-compatible service)
- Internet access (for web search)
- RAM: 512 MB minimum (2 GB recommended)

---

### Supported API Providers

| Provider | Base URL | Models |
|----------|----------|--------|
| Zhipu AI | `https://open.bigmodel.cn/api/paas/v4/` | glm-4.7, glm-4.7-flash |
| OpenAI | `https://api.openai.com/v1` | gpt-4o, gpt-4o-mini |
| DeepSeek | `https://api.deepseek.com/v1` | deepseek-chat |
| Local (Ollama) | `http://localhost:11434/v1` | llama3, qwen2.5, etc. |

---

### License

MIT License · Feel free to use, modify, and distribute.

---

<div align="center">

Made with ❤️ · [Issues](https://github.com/mmlong818/cat-agent/issues) · [Discussions](https://github.com/mmlong818/cat-agent/discussions)

</div>
