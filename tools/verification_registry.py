"""
verification_registry.py - 跨轮次验证注册表
已验证的声明、来源、查询存入此文件，后续步骤直接跳过已验证内容。
注册表路径：{workspace}/08_verification/verified_registry.json
"""
import os
import json
from datetime import datetime

_REGISTRY_FILENAME = os.path.join("08_verification", "verified_registry.json")

def _registry_path(workspace: str) -> str:
    return os.path.join(workspace, _REGISTRY_FILENAME)

def load_registry(workspace: str) -> dict:
    """加载注册表，不存在则返回空注册表"""
    path = _registry_path(workspace)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "verified_claims": {},      # claim_key -> {verdict, confidence, cycle}
        "verified_sources": {},     # url -> {score, tier, confidence_level, cycle}
        "executed_queries": [],     # [query_str, ...]
        "created_at": datetime.now().isoformat()
    }

def save_registry(workspace: str, registry: dict):
    """保存注册表"""
    path = _registry_path(workspace)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    registry["updated_at"] = datetime.now().isoformat()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)

# ── 声明 ──
def _claim_key(claim: str) -> str:
    return claim.strip()[:100]

def is_claim_verified(registry: dict, claim: str) -> bool:
    return _claim_key(claim) in registry.get("verified_claims", {})

def get_claim_result(registry: dict, claim: str) -> dict:
    return registry.get("verified_claims", {}).get(_claim_key(claim), {})

def add_claim_result(registry: dict, claim: str, result: dict, cycle: int = 0):
    registry.setdefault("verified_claims", {})[_claim_key(claim)] = {
        **result, "cycle": cycle, "verified_at": datetime.now().isoformat()
    }

# ── 来源 ──
def is_source_verified(registry: dict, url: str) -> bool:
    return url in registry.get("verified_sources", {})

def add_source_result(registry: dict, url: str, result: dict, cycle: int = 0):
    registry.setdefault("verified_sources", {})[url] = {
        **result, "cycle": cycle, "verified_at": datetime.now().isoformat()
    }

# ── 查询 ──
def is_query_executed(registry: dict, query: str) -> bool:
    return query.strip() in registry.get("executed_queries", [])

def add_executed_query(registry: dict, query: str):
    q = query.strip()
    if q and q not in registry.get("executed_queries", []):
        registry.setdefault("executed_queries", []).append(q)

def get_executed_queries(registry: dict) -> list:
    return registry.get("executed_queries", [])
