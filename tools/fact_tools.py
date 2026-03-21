"""
事实核查工具
提供声明提取和交叉印证搜索功能
"""
import json
import re
from typing import List, Dict, Optional
from tools.web_search import web_search


def cross_reference_search(claim: str, context: str = "", max_queries: int = 3) -> str:
    """
    对特定声明进行多角度交叉验证搜索

    Returns JSON:
    {
      "claim": str,
      "queries_used": [],
      "supporting": [{url, title, snippet, relevance}],
      "contradicting": [{url, title, snippet}],
      "neutral": [],
      "verdict": "supported|disputed|unverifiable|insufficient",
      "confidence": 0.0-1.0,
      "explanation": str
    }
    """
    result = {
        "claim": claim,
        "queries_used": [],
        "supporting": [],
        "contradicting": [],
        "neutral": [],
        "verdict": "insufficient",
        "confidence": 0.0,
        "explanation": ""
    }

    try:
        # 生成多角度搜索查询
        queries = _generate_verification_queries(claim, context, max_queries)
        result["queries_used"] = queries

        all_results = []
        for query in queries:
            try:
                search_result = json.loads(web_search(query, max_results=5))
                if search_result.get("status") == "success":
                    for r in search_result.get("results", []):
                        r["query"] = query
                        all_results.append(r)
            except Exception:
                continue

        if not all_results:
            result["verdict"] = "unverifiable"
            result["explanation"] = "搜索未返回结果，无法验证此声明"
            return json.dumps(result, ensure_ascii=False, indent=2)

        # 分类搜索结果
        claim_keywords = _extract_keywords(claim)
        negation_patterns = ["并非", "不是", "否认", "错误", "误导", "假新闻",
                             "不正确", "质疑", "争议", "fake", "false", "wrong",
                             "incorrect", "dispute", "debunk", "mislead"]

        for r in all_results:
            snippet = r.get("snippet", "") + " " + r.get("title", "")
            snippet_lower = snippet.lower()

            # 检查是否包含核心关键词
            keyword_match = sum(1 for kw in claim_keywords if kw.lower() in snippet_lower)
            has_negation = any(neg in snippet_lower for neg in negation_patterns)

            if keyword_match >= 2:
                if has_negation:
                    result["contradicting"].append({
                        "url": r.get("url", ""),
                        "title": r.get("title", ""),
                        "snippet": r.get("snippet", "")[:200],
                        "relevance": keyword_match
                    })
                else:
                    result["supporting"].append({
                        "url": r.get("url", ""),
                        "title": r.get("title", ""),
                        "snippet": r.get("snippet", "")[:200],
                        "relevance": keyword_match
                    })
            else:
                result["neutral"].append({
                    "url": r.get("url", ""),
                    "title": r.get("title", "")
                })

        # 限制结果数量
        result["supporting"] = result["supporting"][:5]
        result["contradicting"] = result["contradicting"][:3]
        result["neutral"] = result["neutral"][:3]

        # 判断结论
        n_support = len(result["supporting"])
        n_contra = len(result["contradicting"])

        if n_support == 0 and n_contra == 0:
            result["verdict"] = "unverifiable"
            result["confidence"] = 0.2
            result["explanation"] = "未找到直接相关的验证证据"
        elif n_contra > n_support:
            result["verdict"] = "disputed"
            result["confidence"] = max(0.1, 1 - (n_support / max(n_contra + n_support, 1)))
            result["explanation"] = f"发现 {n_contra} 条反驳证据，{n_support} 条支持证据"
        elif n_support >= 3:
            result["verdict"] = "supported"
            result["confidence"] = min(0.9, 0.6 + n_support * 0.1)
            result["explanation"] = f"有 {n_support} 条来源支持此声明"
        elif n_support >= 1:
            result["verdict"] = "supported"
            result["confidence"] = 0.5 + n_support * 0.1
            result["explanation"] = f"有 {n_support} 条来源部分支持此声明，建议进一步验证"
        else:
            result["verdict"] = "insufficient"
            result["confidence"] = 0.3
            result["explanation"] = "证据不足以得出结论"

    except Exception as e:
        result["verdict"] = "error"
        result["explanation"] = f"验证过程出错：{str(e)[:100]}"

    return json.dumps(result, ensure_ascii=False, indent=2)


def _generate_verification_queries(claim: str, context: str, max_queries: int) -> List[str]:
    """生成用于验证声明的多角度搜索查询"""
    queries = []

    # 查询1：直接搜索声明
    queries.append(claim[:100])

    # 查询2：添加"真实性"/"数据"等验证词
    core = claim[:60]
    queries.append(f"{core} 数据来源 研究")

    # 查询3：添加反向验证（是否有质疑）
    if len(queries) < max_queries:
        queries.append(f"{core[:40]} 质疑 争议 错误")

    # 查询4：用英文重复核心内容（如果有数字/英文关键词）
    if len(queries) < max_queries and re.search(r'\d+', claim):
        # 提取数字附近的上下文作为搜索词
        numbers = re.findall(r'\d+[\.,]?\d*[%亿万千百]?', claim)
        if numbers:
            queries.append(f"{numbers[0]} {context[:30]}")

    return queries[:max_queries]


def _extract_keywords(text: str, max_keywords: int = 8) -> List[str]:
    """从声明中提取核心关键词"""
    # 去除停用词
    stopwords = {"的", "了", "在", "是", "和", "与", "或", "等", "也", "都",
                 "这", "那", "有", "为", "从", "到", "被", "对", "以",
                 "the", "a", "an", "is", "are", "was", "were", "in", "on", "at"}

    # 按空格/标点分词
    tokens = re.findall(r'[\w]+', text)
    keywords = [t for t in tokens if t not in stopwords and len(t) > 1]

    # 优先保留数字和较长词汇
    keywords.sort(key=lambda x: (not bool(re.search(r'\d', x)), -len(x)))
    return keywords[:max_keywords]


def cross_reference_search_tool(claim: str, context: str = "", max_queries: int = 3) -> str:
    """智能体工具接口"""
    return cross_reference_search(claim, context, max_queries)
