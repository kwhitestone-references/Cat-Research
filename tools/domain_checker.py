"""
域名权威性检查工具
对来源 URL 进行多维度可信度评估（不依赖第三方 API）
"""
import re
import json
from urllib.parse import urlparse
from typing import Dict, Tuple

# ── Tier 1：最高权威性来源（基础分 90-100）──────────────────────────────────
TIER1_DOMAINS = {
    # 顶级学术期刊
    "nature.com", "science.org", "cell.com", "thelancet.com", "nejm.org",
    "pnas.org", "bmj.com", "jama.jamanetwork.com",
    # 学术数据库/预印本
    "pubmed.ncbi.nlm.nih.gov", "scholar.google.com", "arxiv.org",
    "ieeexplore.ieee.org", "acm.org", "jstor.org", "ssrn.com",
    # 国际权威机构
    "who.int", "un.org", "worldbank.org", "imf.org", "wto.org",
    "oecd.org", "europa.eu", "cdc.gov", "fda.gov",
    # 权威金融/经济媒体
    "ft.com", "economist.com", "wsj.com", "bloomberg.com", "reuters.com",
    "apnews.com",
    # 顶级高校
    "harvard.edu", "stanford.edu", "mit.edu", "oxford.ac.uk",
    "cambridge.ac.uk", "ucl.ac.uk", "yale.edu", "princeton.edu",
}

# ── Tier 2：高可信度来源（基础分 75-89）──────────────────────────────────────
TIER2_DOMAINS = {
    # 主流国际媒体
    "bbc.com", "bbc.co.uk", "nytimes.com", "theguardian.com",
    "washingtonpost.com", "theatlantic.com", "time.com", "cnbc.com",
    "cnn.com", "abc.net.au", "npr.org",
    # 主流科技媒体
    "techcrunch.com", "wired.com", "theverge.com", "arstechnica.com",
    "zdnet.com", "technologyreview.mit.edu", "spectrum.ieee.org",
    # 权威研究机构
    "gartner.com", "forrester.com", "mckinsey.com", "bcg.com",
    "deloitte.com", "pwc.com", "brookings.edu", "rand.org",
    # 数据统计平台
    "statista.com", "ourworldindata.org", "data.worldbank.org",
    # 权威中文来源
    "caixin.com", "yicai.com", "xinhua.net", "china.com.cn",
    "36kr.com", "huxiu.com", "ifeng.com",
    # 知名高校（第二梯队）
    "ucberkeley.edu", "cmu.edu", "caltech.edu", "tsinghua.edu.cn",
    "pku.edu.cn",
}

# ── Tier 3：中等可信度来源（基础分 55-74）────────────────────────────────────
TIER3_DOMAINS = {
    "wikipedia.org", "medium.com", "substack.com", "github.com",
    "stackoverflow.com", "quora.com", "reddit.com",
}

# ── 可疑域名特征（降分）──────────────────────────────────────────────────────
SUSPICIOUS_PATTERNS = [
    r"(free|fake|viral|clickbait|sensational)",
    r"\d{6,}",              # 大量数字（域名生成特征）
    r"(xyz|click|buzz|news\d)",
    r"(-\w+-\w+-\w+\.)",   # 过长的连字符域名
    r"(proxy|mirror|cdn\d+)",
]

# ── TLD 权威性评分 ────────────────────────────────────────────────────────────
TLD_SCORES = {
    ".gov": 92, ".edu": 88, ".org": 68, ".ac.uk": 85, ".ac.jp": 82,
    ".edu.cn": 80, ".gov.cn": 78, ".com": 60, ".net": 58, ".io": 62,
    ".co": 55, ".info": 50, ".xyz": 35, ".top": 35, ".club": 40,
}

# ── 内容类别关键词 ────────────────────────────────────────────────────────────
ACADEMIC_KEYWORDS = ["journal", "research", "study", "institute", "university",
                     "science", "proceedings", "review", "paper", "doi"]
NEWS_KEYWORDS = ["news", "press", "times", "post", "herald", "tribune",
                 "daily", "gazette", "reporter", "media"]
GOVERNMENT_KEYWORDS = ["government", "ministry", "department", "agency",
                       "official", "national", "federal", "bureau"]


def assess_url(url: str) -> Dict:
    """
    评估 URL 的域名权威性，返回详细评分报告

    Returns:
        {
            "url": str,
            "domain": str,
            "tier": int,          # 1/2/3/4 (4=unknown)
            "base_score": int,    # 0-100
            "tld_bonus": int,
            "suspicious_penalty": int,
            "final_score": int,   # 0-100
            "category": str,      # academic/government/news/research/general/unknown
            "confidence_level": str,  # high/medium/low/unknown
            "https": bool,
            "flags": [],
            "assessment": str
        }
    """
    result = {
        "url": url,
        "domain": "",
        "tier": 4,
        "base_score": 40,
        "tld_bonus": 0,
        "suspicious_penalty": 0,
        "final_score": 40,
        "category": "unknown",
        "confidence_level": "unknown",
        "https": False,
        "flags": [],
        "assessment": ""
    }

    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            result["flags"].append("invalid_url")
            result["final_score"] = 0
            result["assessment"] = "无效 URL"
            return result

        domain = parsed.netloc.lower()
        # 移除 www. 前缀
        if domain.startswith("www."):
            domain = domain[4:]
        result["domain"] = domain
        result["https"] = parsed.scheme == "https"

        # ── 1. 域名 Tier 分类 ────────────────────────────────────────────
        if domain in TIER1_DOMAINS or any(domain.endswith("." + d) for d in TIER1_DOMAINS):
            result["tier"] = 1
            result["base_score"] = 90
        elif domain in TIER2_DOMAINS or any(domain.endswith("." + d) for d in TIER2_DOMAINS):
            result["tier"] = 2
            result["base_score"] = 75
        elif domain in TIER3_DOMAINS:
            result["tier"] = 3
            result["base_score"] = 60
        else:
            result["tier"] = 4
            result["base_score"] = 45  # 未知域名基础分

        # ── 2. TLD 加权 ────────────────────────────────────────────────
        tld_bonus = 0
        for tld, score in TLD_SCORES.items():
            if domain.endswith(tld):
                # 只在 tier 4 (未知域名) 时用 TLD 加权
                if result["tier"] == 4:
                    tld_bonus = max(0, score - 60)  # 换算为加成值
                break
        result["tld_bonus"] = tld_bonus

        # ── 3. 类别识别 ──────────────────────────────────────────────────
        if domain.endswith(".gov") or domain.endswith(".gov.cn"):
            result["category"] = "government"
            if result["tier"] == 4:
                result["base_score"] = max(result["base_score"], 72)
        elif domain.endswith(".edu") or domain.endswith(".edu.cn") or domain.endswith(".ac.uk"):
            result["category"] = "academic"
            if result["tier"] == 4:
                result["base_score"] = max(result["base_score"], 68)
        elif any(kw in domain for kw in ACADEMIC_KEYWORDS):
            result["category"] = "academic"
        elif any(kw in domain for kw in NEWS_KEYWORDS):
            result["category"] = "news"
        elif any(kw in domain for kw in GOVERNMENT_KEYWORDS):
            result["category"] = "government"
        else:
            result["category"] = "general"

        # ── 4. 可疑模式检测（降分）──────────────────────────────────────
        suspicious_penalty = 0
        for pattern in SUSPICIOUS_PATTERNS:
            if re.search(pattern, domain, re.IGNORECASE):
                suspicious_penalty += 15
                result["flags"].append(f"suspicious_pattern:{pattern[:20]}")

        # HTTPS 加成
        https_bonus = 5 if result["https"] else -10
        if not result["https"]:
            result["flags"].append("no_https")

        result["suspicious_penalty"] = suspicious_penalty

        # ── 5. 最终评分计算 ──────────────────────────────────────────────
        final_score = result["base_score"] + tld_bonus + https_bonus - suspicious_penalty
        result["final_score"] = max(0, min(100, final_score))

        # ── 6. 置信度等级 ──────────────────────────────────────────────
        score = result["final_score"]
        if score >= 80:
            result["confidence_level"] = "high"
        elif score >= 60:
            result["confidence_level"] = "medium"
        elif score >= 40:
            result["confidence_level"] = "low"
        else:
            result["confidence_level"] = "very_low"

        # ── 7. 评估描述 ──────────────────────────────────────────────
        tier_names = {1: "顶级权威来源", 2: "高可信来源", 3: "中等可信来源", 4: "一般来源"}
        result["assessment"] = (
            f"{tier_names.get(result['tier'], '未知')}"
            f" | 置信度：{result['confidence_level']}"
            f" | 分类：{result['category']}"
        )
        if result["flags"]:
            result["assessment"] += f" | 警告：{', '.join(result['flags'])}"

    except Exception as e:
        result["flags"].append(f"error:{str(e)[:50]}")
        result["assessment"] = f"评估失败：{str(e)[:100]}"

    return result


def assess_source_list(sources: list) -> Dict:
    """
    批量评估来源列表，返回汇总报告

    Args:
        sources: [{"url": ..., "title": ...}, ...]

    Returns:
        {
            "sources": [assessed_sources...],
            "summary": {
                "total": int,
                "high_confidence": int,
                "medium_confidence": int,
                "low_confidence": int,
                "average_score": float,
                "overall_quality": str
            }
        }
    """
    assessed = []
    for src in sources:
        url = src.get("url", "") if isinstance(src, dict) else str(src)
        assessment = assess_url(url)
        if isinstance(src, dict):
            assessment.update({k: v for k, v in src.items() if k not in assessment})
        assessed.append(assessment)

    scores = [s["final_score"] for s in assessed]
    avg_score = sum(scores) / len(scores) if scores else 0

    summary = {
        "total": len(assessed),
        "high_confidence": sum(1 for s in assessed if s["confidence_level"] == "high"),
        "medium_confidence": sum(1 for s in assessed if s["confidence_level"] == "medium"),
        "low_confidence": sum(1 for s in assessed if s["confidence_level"] in ("low", "very_low")),
        "average_score": round(avg_score, 1),
        "overall_quality": (
            "excellent" if avg_score >= 80 else
            "good" if avg_score >= 65 else
            "fair" if avg_score >= 50 else
            "poor"
        )
    }

    return {"sources": assessed, "summary": summary}


def check_domain_authority(url: str) -> str:
    """智能体工具接口 - 返回 JSON 字符串"""
    result = assess_url(url)
    return json.dumps(result, ensure_ascii=False, indent=2)
