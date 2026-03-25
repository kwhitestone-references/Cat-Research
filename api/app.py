"""
FastAPI 应用 - 多智能体研究系统 REST API
支持 SSE 实时流式进度推送
"""
import os
import json
import asyncio
import threading
import time
import uuid
from datetime import datetime
from typing import Optional, AsyncGenerator
from queue import Queue, Empty

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# 项目根目录
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(ROOT_DIR, "static")
WORKSPACE_DIR = os.path.join(ROOT_DIR, "workspace")

app = FastAPI(
    title="多智能体研究系统 API",
    description="基于 Claude 的多智能体研究系统，支持来源验证、事实核查和结论验证",
    version="2.0.0"
)

# CORS 配置
# 生产环境请将 CORS_ORIGINS 环境变量设置为实际前端域名，如：
# CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
_cors_origins_env = os.getenv("CORS_ORIGINS", "")
_cors_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()] or ["http://localhost:3000", "http://localhost:8000", "http://127.0.0.1:8000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Accept"],
)

# 挂载静态文件
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ── 请求/响应模型 ────────────────────────────────────────────────────────────

class ResearchRequest(BaseModel):
    question: str
    clarification: Optional[str] = None  # 预填写的澄清信息
    research_strategy: Optional[str] = None  # 研究策略（搜索方向、来源类型等）
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    core_model: Optional[str] = None
    support_model: Optional[str] = None
    min_cycles: Optional[int] = None
    max_cycles: Optional[int] = None
    quality_threshold: Optional[float] = None
    timeout_sec: Optional[int] = None  # 单次任务超时时间（秒）


class ConfigRequest(BaseModel):
    model: Optional[str] = None          # 兼容旧字段（映射到 core_model）
    core_model: Optional[str] = None
    support_model: Optional[str] = None
    min_cycles: Optional[int] = None
    max_cycles: Optional[int] = None
    quality_threshold: Optional[float] = None


class SettingsRequest(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    core_model: Optional[str] = None
    support_model: Optional[str] = None
    min_cycles: Optional[int] = None
    max_cycles: Optional[int] = None
    quality_threshold: Optional[float] = None


class ClarifyStartRequest(BaseModel):
    question: str

class ClarifyReplyRequest(BaseModel):
    message: str

class ClarifyConfirmRequest(BaseModel):
    summary: Optional[dict] = None   # 用户可编辑后的摘要
    extra_note: Optional[str] = None # 用户额外补充（可选）


# ── 会话管理 ─────────────────────────────────────────────────────────────────

# 最大并发研究任务数
MAX_CONCURRENT_TASKS = 2

# ── 澄清会话存储 {clarify_id: dict} ─────────────────────────────────────────
_clarify_sessions: dict[str, dict] = {}

# 存储活跃任务的事件队列 {task_id: Queue}
_task_queues: dict[str, Queue] = {}
# 存储任务状态 {task_id: dict}
_task_status: dict[str, dict] = {}
# 存储各任务的 orchestrator 引用（用于注入消息和暂停控制）
_task_orchestrators: dict[str, object] = {}
# 存储各任务的暂停事件 {task_id: threading.Event}
_task_pause_events: dict[str, threading.Event] = {}
# 存储各任务的停止事件 {task_id: threading.Event}
_task_stop_events: dict[str, threading.Event] = {}

_MAX_RECENT_EVENTS = 8
try:
    _STATUS_IDLE_TIMEOUT_SEC = max(0, int(os.getenv("STATUS_IDLE_TIMEOUT_SEC", "300")))
except ValueError:
    _STATUS_IDLE_TIMEOUT_SEC = 300
_PHASE_PROGRESS = {
    1.0: 0.08,
    2.0: 0.18,
    3.0: 0.34,
    3.5: 0.46,
    4.0: 0.58,
    5.0: 0.68,
    6.0: 0.72,
    7.0: 0.95,
}
_IMPROVEMENT_PROGRESS_BASE = 0.72
_IMPROVEMENT_PROGRESS_SPAN = 0.20


def _running_task_count() -> int:
    """返回当前正在运行的任务数量"""
    return sum(1 for s in _task_status.values() if s.get("status") == "running")


def _get_task_status(task_id: str) -> dict:
    return _task_status.get(task_id, {"status": "not_found"})


def _touch_task_observation(task_id: str):
    status = _task_status.get(task_id)
    if not status:
        return
    now = time.time()
    status["last_observed_ts"] = now
    status["last_observed_at"] = datetime.fromtimestamp(now).isoformat()


def _clamp_progress(value: float) -> float:
    return max(0.0, min(1.0, value))


def _set_task_progress(task_id: str, progress: float, *, force: bool = False):
    status = _task_status.get(task_id)
    if not status:
        return
    progress = _clamp_progress(progress)
    current = float(status.get("progress", 0.0) or 0.0)
    if force or progress > current:
        status["progress"] = progress


def _update_progress_from_phase(task_id: str, phase: object):
    try:
        phase_value = float(phase)
    except (TypeError, ValueError):
        return
    progress = _PHASE_PROGRESS.get(phase_value)
    if progress is not None:
        _set_task_progress(task_id, progress)


def _update_progress_from_cycle(task_id: str, cycle: object, max_cycles: object):
    try:
        cycle_value = int(cycle)
    except (TypeError, ValueError):
        return
    try:
        max_cycle_value = int(max_cycles)
    except (TypeError, ValueError):
        max_cycle_value = 0

    if cycle_value <= 0:
        return
    if max_cycle_value <= 0:
        max_cycle_value = max(cycle_value, 1)

    cycle_fraction = min(cycle_value, max_cycle_value) / max_cycle_value
    progress = _IMPROVEMENT_PROGRESS_BASE + (cycle_fraction * _IMPROVEMENT_PROGRESS_SPAN)
    _set_task_progress(task_id, progress)


def _put_event(task_id: str, event_type: str, data: dict):
    """向任务队列推送事件"""
    if task_id in _task_queues:
        _task_queues[task_id].put({
            "type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        })


def _build_event_summary(event_type: str, data: dict) -> Optional[str]:
    if event_type == "started":
        question = (data or {}).get("question", "")
        return f"任务开始：{question[:60]}" if question else "任务开始"
    if event_type == "phase":
        name = (data or {}).get("name", "")
        return f"进入阶段：{name}" if name else None
    if event_type == "status":
        status_text = (data or {}).get("status", "")
        return f"当前状态：{status_text}" if status_text else None
    if event_type == "tool_call":
        return (data or {}).get("message")
    if event_type == "plan":
        total_queries = len((data or {}).get("search_queries", []) or [])
        total_aspects = len((data or {}).get("key_aspects", []) or [])
        return f"研究规划完成：{total_aspects} 个维度，{total_queries} 个查询"
    if event_type == "cycle_start":
        cycle = (data or {}).get("cycle")
        max_cycle = (data or {}).get("max")
        if cycle and max_cycle:
            return f"开始第 {cycle}/{max_cycle} 轮改进"
    if event_type == "review":
        avg_score = (data or {}).get("avg_score")
        if avg_score is not None:
            return f"评审完成：平均分 {avg_score}"
    if event_type == "confidence_report":
        return "置信度报告已生成"
    if event_type == "paused":
        phase = (data or {}).get("phase", "")
        return f"任务已暂停（阶段：{phase}）" if phase else "任务已暂停"
    if event_type == "resumed":
        phase = (data or {}).get("phase", "")
        return f"任务已恢复（阶段：{phase}）" if phase else "任务已恢复"
    if event_type == "user_message_ack":
        msgs = (data or {}).get("messages", []) or []
        if msgs:
            return f"收到用户补充：{'; '.join(str(m) for m in msgs)[:120]}"
    if event_type == "completed":
        return "研究任务完成"
    if event_type == "error":
        msg = (data or {}).get("message", "")
        return msg or "任务执行失败"
    return None


def _record_task_event(task_id: str, event_type: str, data: dict):
    status = _task_status.get(task_id)
    if not status:
        return

    summary = _build_event_summary(event_type, data)
    if not summary:
        return

    timestamp = datetime.now().isoformat()
    recent_events = status.setdefault("recent_events", [])
    recent_events.append({
        "type": event_type,
        "summary": summary,
        "timestamp": timestamp,
    })
    if len(recent_events) > _MAX_RECENT_EVENTS:
        del recent_events[:-_MAX_RECENT_EVENTS]

    status["last_event"] = summary
    if event_type != "error":
        status["message"] = summary


def _heartbeat_thread(task_id: str, stop_ev):
    """每 8 秒推送一次心跳，告知前端任务仍在运行"""
    import time as _time
    while not stop_ev.is_set():
        stop_ev.wait(timeout=8)
        if stop_ev.is_set():
            break
        st = _task_status.get(task_id, {})
        if st.get("status") not in ("running",):
            break
        _put_event(task_id, "heartbeat", {
            "current_status": st.get("current_status", ""),
            "current_cycle": st.get("current_cycle", 0),
            "elapsed": round(_time.time() - st.get("_start_ts", _time.time()))
        })


def _status_idle_watchdog(task_id: str, idle_timeout_sec: int, stop_ev, pause_ev):
    """超过指定时间无人查询状态或订阅进度时，自动停止任务。"""
    if idle_timeout_sec <= 0:
        return

    while not stop_ev.is_set():
        stop_ev.wait(timeout=min(5.0, idle_timeout_sec))
        if stop_ev.is_set():
            return

        status = _task_status.get(task_id)
        if not status:
            return
        if status.get("status") not in ("pending", "running"):
            return

        last_observed = float(
            status.get("last_observed_ts")
            or status.get("_start_ts")
            or time.time()
        )
        if time.time() - last_observed < idle_timeout_sec:
            continue

        status["idle_timeout_triggered"] = True
        status["status"] = "stopped"
        status["current_status"] = "stopped"
        status["message"] = f"超过{idle_timeout_sec}秒未查询状态，任务已自动停止"
        _set_task_progress(task_id, 1.0, force=True)
        _put_event(task_id, "error", {"message": status["message"]})
        _record_task_event(task_id, "error", {"message": status["message"]})
        if pause_ev:
            pause_ev.set()
        stop_ev.set()
        return


def _timeout_watchdog(task_id: str, timeout_sec: int, stop_ev, pause_ev):
    """到达单次任务超时后，请求任务停止并标记失败。"""
    if timeout_sec <= 0:
        return
    deadline = time.time() + timeout_sec
    while not stop_ev.is_set():
        remaining = deadline - time.time()
        if remaining <= 0:
            status = _task_status.get(task_id)
            if not status:
                return
            if status.get("status") not in ("pending", "running"):
                return
            status["timeout_triggered"] = True
            status["status"] = "failed"
            status["current_status"] = "timeout"
            status["message"] = f"任务执行超时（>{timeout_sec}s），正在停止..."
            _put_event(task_id, "error", {"message": status["message"]})
            _record_task_event(task_id, "error", {"message": status["message"]})
            if pause_ev:
                pause_ev.set()
            stop_ev.set()
            return
        stop_ev.wait(timeout=min(1.0, max(0.1, remaining)))


def _build_task_runtime_config(task_status: dict) -> dict:
    import config

    return {
        "api_key": task_status.get("api_key") or config.API_KEY,
        "base_url": task_status.get("base_url") or config.API_BASE_URL,
        "core_model": task_status.get("core_model") or config.CORE_MODEL,
        "support_model": task_status.get("support_model") or config.SUPPORT_MODEL,
        "min_cycles": task_status.get("min_cycles") or config.MIN_IMPROVEMENT_CYCLES,
        "max_cycles": task_status.get("max_cycles") or config.MAX_IMPROVEMENT_CYCLES,
        "quality_threshold": task_status.get("quality_threshold"),
    }


def _apply_task_runtime_config(task_config: dict):
    import config
    from agents import planner, researcher, analyst, writer, critic, source_verifier, fact_checker, conclusion_validator
    import orchestrator as orchestrator_module

    api_key = (task_config.get("api_key") or "").strip()
    if api_key:
        config.API_KEY = api_key
        config.ZHIPU_API_KEY = api_key
        config.ANTHROPIC_API_KEY = api_key

    base_url = (task_config.get("base_url") or "").strip()
    if base_url:
        normalized = config.normalize_openai_base_url(base_url)
        config.API_BASE_URL = normalized
        config.ZHIPU_BASE_URL = normalized

    core_model = (task_config.get("core_model") or "").strip()
    if core_model:
        config.CORE_MODEL = core_model
        config.ORCHESTRATOR_MODEL = core_model
        config.PLANNER_MODEL = core_model
        config.RESEARCHER_MODEL = core_model
        config.ANALYST_MODEL = core_model
        config.WRITER_MODEL = core_model
        orchestrator_module.ORCHESTRATOR_MODEL = core_model
        planner.PLANNER_MODEL = core_model
        researcher.RESEARCHER_MODEL = core_model
        analyst.ANALYST_MODEL = core_model
        writer.WRITER_MODEL = core_model

    support_model = (task_config.get("support_model") or "").strip()
    if support_model:
        config.SUPPORT_MODEL = support_model
        config.CRITIC_MODEL = support_model
        config.SOURCE_VERIFIER_MODEL = support_model
        config.FACT_CHECKER_MODEL = support_model
        config.CONCLUSION_VALIDATOR_MODEL = support_model
        critic.CRITIC_MODEL = support_model
        source_verifier.SOURCE_VERIFIER_MODEL = support_model
        fact_checker.FACT_CHECKER_MODEL = support_model
        conclusion_validator.CONCLUSION_VALIDATOR_MODEL = support_model

    min_cycles = task_config.get("min_cycles")
    if min_cycles is not None:
        config.MIN_IMPROVEMENT_CYCLES = int(min_cycles)
        orchestrator_module.MIN_IMPROVEMENT_CYCLES = int(min_cycles)

    max_cycles = task_config.get("max_cycles")
    if max_cycles is not None:
        config.MAX_IMPROVEMENT_CYCLES = int(max_cycles)
        orchestrator_module.MAX_IMPROVEMENT_CYCLES = int(max_cycles)

    quality_threshold = task_config.get("quality_threshold")
    if quality_threshold is not None:
        config.QUALITY_THRESHOLD = float(quality_threshold)
        orchestrator_module.QUALITY_THRESHOLD = float(quality_threshold)


def _run_research_task(task_id: str, question: str, clarification: Optional[str],
                       research_strategy: Optional[str] = None,
                       intent_meta: Optional[dict] = None,
                       timeout_sec: Optional[int] = None):
    """在后台线程中运行研究任务"""
    import sys, time as _time
    sys.path.insert(0, ROOT_DIR)
    # orchestrator.py 在模块加载时已全局替换 stdout/stderr 为 UTF-8，
    # 线程内不再重复替换，否则会产生 "I/O operation on closed file" 错误

    try:
        _task_status[task_id]["status"] = "running"
        _task_status[task_id]["_start_ts"] = _time.time()
        _set_task_progress(task_id, 0.01, force=True)
        _put_event(task_id, "started", {"task_id": task_id, "question": question})
        _record_task_event(task_id, "started", {"task_id": task_id, "question": question})

        # 启动心跳线程
        hb_stop = _task_stop_events.get(task_id) or threading.Event()
        hb_thread = threading.Thread(target=_heartbeat_thread, args=(task_id, hb_stop), daemon=True)
        hb_thread.start()

        task_config = _build_task_runtime_config(_task_status[task_id])
        if not task_config.get("api_key"):
            raise RuntimeError("未提供 API Key，无法启动研究任务")
        _apply_task_runtime_config(task_config)

        # 启动单任务超时守护线程
        effective_timeout = int(timeout_sec or 0)
        pause_event = _task_pause_events.get(task_id)
        stop_event = _task_stop_events.get(task_id)
        if effective_timeout > 0:
            watchdog_thread = threading.Thread(
                target=_timeout_watchdog,
                args=(task_id, effective_timeout, hb_stop, pause_event),
                daemon=True,
            )
            watchdog_thread.start()

        idle_watchdog_thread = threading.Thread(
            target=_status_idle_watchdog,
            args=(task_id, _STATUS_IDLE_TIMEOUT_SEC, hb_stop, pause_event),
            daemon=True,
        )
        idle_watchdog_thread.start()

        # 如果有预填写的澄清信息，合并到问题中
        full_question = question
        if clarification:
            full_question = f"{question}\n\n补充说明：{clarification}"

        from orchestrator import ResearchOrchestrator

        def progress_callback(event_type: str, data: dict):
            try:
                _put_event(task_id, event_type, data)
                _record_task_event(task_id, event_type, data)
                # 同步更新状态
                if event_type == "status":
                    _task_status[task_id]["current_status"] = data.get("status", "")
                elif event_type == "phase":
                    _task_status[task_id]["phase"] = data.get("name") or data.get("phase")
                    if data.get("name"):
                        _task_status[task_id]["current_status"] = data.get("name", "")
                    _update_progress_from_phase(task_id, data.get("phase"))
                elif event_type == "plan":
                    _task_status[task_id]["plan"] = data
                elif event_type == "cycle_start":
                    _task_status[task_id]["current_cycle"] = data.get("cycle", 0)
                    _task_status[task_id]["max_cycles"] = data.get("max", _task_status[task_id].get("max_cycles", 0))
                    _update_progress_from_cycle(task_id, data.get("cycle"), data.get("max"))
                elif event_type == "review":
                    scores = _task_status[task_id].get("scores", [])
                    scores.append(data.get("avg_score", 0))
                    _task_status[task_id]["scores"] = scores
                    _update_progress_from_cycle(
                        task_id,
                        data.get("cycle", _task_status[task_id].get("current_cycle", 0)),
                        _task_status[task_id].get("max_cycles", 0),
                    )
                elif event_type == "confidence_report":
                    _task_status[task_id]["confidence_report"] = data
                elif event_type == "token_usage":
                    usage = _task_status[task_id].setdefault("token_usage", {
                        "total_input_tokens": 0,
                        "total_output_tokens": 0,
                        "by_agent": {}
                    })
                    agent_name = data.get("agent", "unknown")
                    usage["total_input_tokens"] += data.get("turn_input", 0)
                    usage["total_output_tokens"] += data.get("turn_output", 0)
                    agent_usage = usage["by_agent"].setdefault(agent_name, {
                        "input_tokens": 0, "output_tokens": 0, "calls": 0
                    })
                    agent_usage["input_tokens"] += data.get("turn_input", 0)
                    agent_usage["output_tokens"] += data.get("turn_output", 0)
                    agent_usage["calls"] += 1
            except Exception:
                pass  # 回调失败不中断主流程

        orchestrator = ResearchOrchestrator(progress_callback=progress_callback)
        _task_orchestrators[task_id] = orchestrator

        # 注入澄清信息跳过交互式输入
        if clarification:
            import unittest.mock as mock
            with mock.patch('builtins.input', return_value=clarification):
                result = orchestrator.run(full_question, research_strategy=research_strategy,
                                         intent_meta=intent_meta,
                                         pause_event=pause_event, stop_event=stop_event)
        else:
            result = orchestrator.run(full_question, research_strategy=research_strategy,
                                      intent_meta=intent_meta,
                                      pause_event=pause_event, stop_event=stop_event)

        interrupted = (stop_event is not None and stop_event.is_set()) or result == "任务已中断"
        if interrupted:
            final_status = _task_status[task_id].get("status")
            if _task_status[task_id].get("timeout_triggered"):
                final_status = "failed"
                _task_status[task_id]["message"] = f"任务执行超时（>{effective_timeout}s）"
                _task_status[task_id]["error"] = _task_status[task_id]["message"]
            elif _task_status[task_id].get("idle_timeout_triggered"):
                final_status = "stopped"
                _task_status[task_id]["error"] = _task_status[task_id].get("message", "任务已自动停止")
            elif final_status not in ("deleted", "stopped"):
                final_status = "stopped"
            _task_status[task_id]["status"] = final_status
            _task_status[task_id]["current_status"] = final_status
            if final_status == "stopped" and not _task_status[task_id].get("idle_timeout_triggered"):
                _task_status[task_id]["message"] = "任务已停止"
            _set_task_progress(task_id, 1.0, force=True)
            _task_status[task_id]["workspace"] = str(orchestrator.workspace)
            _task_status[task_id]["session_id"] = orchestrator.session_id
            return

        _task_status[task_id]["status"] = "completed"
        _set_task_progress(task_id, 1.0, force=True)
        _task_status[task_id]["result"] = result
        _task_status[task_id]["workspace"] = str(orchestrator.workspace)
        _task_status[task_id]["session_id"] = orchestrator.session_id

        # Collect final token stats from orchestrator agents
        token_usage = _task_status[task_id].get("token_usage", {
            "total_input_tokens": 0, "total_output_tokens": 0, "by_agent": {}
        })
        for agent in [orchestrator.planner, orchestrator.researcher,
                      orchestrator.analyst, orchestrator.writer,
                      orchestrator.critic, orchestrator.source_verifier,
                      orchestrator.fact_checker, orchestrator.conclusion_validator]:
            name = getattr(agent, "name", type(agent).__name__)
            inp = getattr(agent, "_total_input_tokens", 0)
            out = getattr(agent, "_total_output_tokens", 0)
            if inp or out:
                existing = token_usage["by_agent"].get(name, {
                    "input_tokens": 0, "output_tokens": 0, "calls": 0
                })
                # Use max of callback-tracked vs agent-tracked (in-process they match)
                existing["input_tokens"] = max(existing.get("input_tokens", 0), inp)
                existing["output_tokens"] = max(existing.get("output_tokens", 0), out)
                token_usage["by_agent"][name] = existing
        # Recompute totals from by_agent
        token_usage["total_input_tokens"] = sum(
            a.get("input_tokens", 0) for a in token_usage["by_agent"].values()
        )
        token_usage["total_output_tokens"] = sum(
            a.get("output_tokens", 0) for a in token_usage["by_agent"].values()
        )
        _task_status[task_id]["token_usage"] = token_usage

        _put_event(task_id, "completed", {
            "result": result[:500] + "..." if len(result) > 500 else result,
            "workspace": str(orchestrator.workspace),
            "session_id": orchestrator.session_id,
            "token_usage": token_usage
        })
        _record_task_event(task_id, "completed", {
            "workspace": str(orchestrator.workspace),
            "session_id": orchestrator.session_id,
        })

    except Exception as e:
        error_msg = str(e)
        _task_status[task_id]["status"] = "failed"
        _set_task_progress(task_id, 1.0, force=True)
        _task_status[task_id]["error"] = error_msg
        _put_event(task_id, "error", {"message": error_msg})
        _record_task_event(task_id, "error", {"message": error_msg})

    finally:
        # 发送结束标记
        _put_event(task_id, "end", {})


# ── API 路由 ─────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    """提供 Web UI"""
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse({"message": "多智能体研究系统 API v2.0", "docs": "/docs"})


@app.post("/api/research")
async def start_research(request: ResearchRequest):
    """
    启动一个新的研究任务（最多同时运行 MAX_CONCURRENT_TASKS 个）
    返回 task_id，通过 /api/research/{task_id}/stream 获取实时进度
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="研究问题不能为空")

    running = _running_task_count()
    if running >= MAX_CONCURRENT_TASKS:
        raise HTTPException(
            status_code=429,
            detail=f"当前已有 {running} 个任务在运行，最多支持 {MAX_CONCURRENT_TASKS} 个并发研究，请等待现有任务完成后再提交。"
        )

    task_id = str(uuid.uuid4())[:8]
    _task_queues[task_id] = Queue()
    pause_ev = threading.Event()
    pause_ev.set()  # 初始为"未暂停"状态
    _task_pause_events[task_id] = pause_ev
    stop_ev = threading.Event()  # 初始未设置（未停止）
    _task_stop_events[task_id] = stop_ev
    _task_status[task_id] = {
        "task_id": task_id,
        "question": request.question,
        "api_key": request.api_key,
        "base_url": request.base_url,
        "core_model": request.core_model,
        "support_model": request.support_model,
        "min_cycles": request.min_cycles,
        "max_cycles": request.max_cycles,
        "quality_threshold": request.quality_threshold,
        "status": "pending",
        "progress": 0.0,
        "created_at": datetime.now().isoformat(),
        "last_observed_ts": time.time(),
        "scores": [],
        "current_cycle": 0,
        "timeout_sec": request.timeout_sec,
    }

    # 在后台线程中运行
    thread = threading.Thread(
        target=_run_research_task,
        args=(task_id, request.question, request.clarification, request.research_strategy, None, request.timeout_sec),
        daemon=True
    )
    thread.start()

    return {
        "task_id": task_id,
        "status": "started",
        "stream_url": f"/api/research/{task_id}/stream",
        "status_url": f"/api/research/{task_id}/status"
    }


@app.get("/api/research/{task_id}/stream")
async def stream_progress(task_id: str):
    """
    SSE 流式获取研究进度
    每个事件格式：data: {json}\n\n
    """
    if task_id not in _task_queues:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    async def event_generator() -> AsyncGenerator[str, None]:
        _touch_task_observation(task_id)
        # 心跳，保持连接
        yield f"data: {json.dumps({'type': 'ping', 'task_id': task_id})}\n\n"

        queue = _task_queues[task_id]
        end_received = False

        while not end_received:
            # 非阻塞读取队列（100ms 超时）
            try:
                await asyncio.sleep(0.1)
                _touch_task_observation(task_id)
                while True:
                    try:
                        event = queue.get_nowait()
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                        if event.get("type") == "end":
                            end_received = True
                            break
                    except Empty:
                        break
            except asyncio.CancelledError:
                break

        # 清理队列（但保留状态）
        if task_id in _task_queues:
            del _task_queues[task_id]

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )


@app.get("/api/research/{task_id}/status")
async def get_task_status(task_id: str):
    """获取任务状态快照"""
    status = _get_task_status(task_id)
    if status.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    _touch_task_observation(task_id)
    return status


@app.get("/api/research/{task_id}/result")
async def get_task_result(task_id: str):
    """获取已完成任务的完整结果"""
    status = _get_task_status(task_id)
    if status.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    if status.get("status") != "completed":
        raise HTTPException(status_code=425, detail=f"任务尚未完成，当前状态: {status.get('status')}")
    return {
        "task_id": task_id,
        "result": status.get("result", ""),
        "workspace": status.get("workspace", ""),
        "session_id": status.get("session_id", ""),
        "confidence_report": status.get("confidence_report", {}),
        "plan": status.get("plan", {}),
        "token_usage": status.get("token_usage", {})
    }


@app.get("/api/sessions")
async def list_sessions():
    """列出所有研究会话"""
    sessions = []
    if not os.path.exists(WORKSPACE_DIR):
        return {"sessions": []}

    for name in sorted(os.listdir(WORKSPACE_DIR), reverse=True):
        session_path = os.path.join(WORKSPACE_DIR, name)
        if not os.path.isdir(session_path):
            continue
        meta_file = os.path.join(session_path, "00_session.json")
        if os.path.exists(meta_file):
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                sessions.append({
                    "session_id": meta.get("session_id", name),
                    "question": meta.get("question", "")[:100],
                    "status": meta.get("status", "unknown"),
                    "created_at": meta.get("created_at", ""),
                    "final_score": meta.get("final_score", None),
                    "total_cycles": meta.get("total_cycles", None)
                })
            except Exception:
                sessions.append({"session_id": name, "status": "unknown"})

    return {"sessions": sessions[:20]}


@app.post("/api/research/{task_id}/message")
async def send_message(task_id: str, body: dict):
    """向正在运行的任务注入用户消息（在下一个阶段检查点生效）"""
    msg = (body.get("message") or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="消息不能为空")
    orchestrator = _task_orchestrators.get(task_id)
    if not orchestrator:
        raise HTTPException(status_code=404, detail="任务不存在或已完成")
    orchestrator._user_messages.append(msg)
    _put_event(task_id, "user_message_queued", {"message": msg})
    return {"status": "queued", "message": msg}


@app.post("/api/research/{task_id}/stop")
async def stop_task(task_id: str):
    """立即停止正在运行的任务"""
    stop_ev = _task_stop_events.get(task_id)
    if stop_ev:
        stop_ev.set()
    # 同时解除暂停（若已暂停则让线程继续运行到停止检查点）
    pause_ev = _task_pause_events.get(task_id)
    if pause_ev:
        pause_ev.set()
    if task_id in _task_status:
        _task_status[task_id]["status"] = "stopped"
        _task_status[task_id]["current_status"] = "stopped"
        _task_status[task_id]["message"] = "任务已被用户停止"
        _set_task_progress(task_id, 1.0, force=True)
    _put_event(task_id, "error", {"message": "任务已被用户停止"})
    return {"status": "stopping"}


@app.delete("/api/research/{task_id}")
async def delete_task(task_id: str):
    """停止并删除任务（含工作区目录）"""
    import shutil, time as _t
    # 先停止
    stop_ev = _task_stop_events.get(task_id)
    if stop_ev:
        stop_ev.set()
    pause_ev = _task_pause_events.get(task_id)
    if pause_ev:
        pause_ev.set()
    if task_id in _task_status:
        _task_status[task_id]["status"] = "deleted"
    _put_event(task_id, "error", {"message": "任务已删除"})
    # 短暂等待线程响应停止信号
    await asyncio.sleep(0.5)
    # 删除工作区
    workspace = _task_status.get(task_id, {}).get("workspace")
    if workspace and os.path.isdir(workspace):
        shutil.rmtree(workspace, ignore_errors=True)
    else:
        # 尝试从会话 ID 查找
        session_id = _task_status.get(task_id, {}).get("session_id")
        if session_id:
            ws = _find_workspace(session_id)
            if os.path.isdir(ws):
                shutil.rmtree(ws, ignore_errors=True)
    # 清理内存状态
    for d in [_task_status, _task_queues, _task_pause_events, _task_stop_events, _task_orchestrators]:
        d.pop(task_id, None)
    return {"status": "deleted", "task_id": task_id}


@app.post("/api/research/{task_id}/pause")
async def pause_task(task_id: str):
    """暂停正在运行的任务"""
    ev = _task_pause_events.get(task_id)
    if not ev:
        raise HTTPException(status_code=404, detail="任务不存在")
    ev.clear()  # 清除事件 → orchestrator 在检查点阻塞
    _task_status[task_id]["paused"] = True
    return {"status": "pausing"}


@app.post("/api/research/{task_id}/resume")
async def resume_task(task_id: str):
    """恢复已暂停的任务"""
    ev = _task_pause_events.get(task_id)
    if not ev:
        raise HTTPException(status_code=404, detail="任务不存在")
    ev.set()  # 设置事件 → orchestrator 继续运行
    _task_status[task_id]["paused"] = False
    return {"status": "resumed"}


def _find_workspace_or_none(session_id: str):
    """按 session_id 查找工作空间路径，不存在返回 None"""
    if os.path.exists(WORKSPACE_DIR):
        for name in os.listdir(WORKSPACE_DIR):
            if session_id in name:
                return os.path.join(WORKSPACE_DIR, name)
    return None


@app.get("/api/sessions/{session_id}/report")
async def get_session_report(session_id: str):
    """获取指定会话的最终报告"""
    workspace = _find_workspace_or_none(session_id)
    if not workspace:
        raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在")

    final_file = os.path.join(workspace, "09_final.md")
    if not os.path.exists(final_file):
        raise HTTPException(status_code=404, detail="最终报告尚未生成")

    with open(final_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 尝试读取置信度报告
    conf_file = os.path.join(workspace, "08_verification", "confidence_report.json")
    confidence_report = {}
    if os.path.exists(conf_file):
        with open(conf_file, 'r', encoding='utf-8') as f:
            try:
                confidence_report = json.load(f)
            except Exception:
                pass

    return {
        "session_id": session_id,
        "report": content,
        "confidence_report": confidence_report
    }


@app.get("/api/sessions/{session_id}/plan")
async def get_session_plan(session_id: str):
    """获取指定会话的研究计划"""
    workspace = _find_workspace(session_id)
    plan_file = os.path.join(workspace, "03_plan.json")
    if not os.path.exists(plan_file):
        raise HTTPException(status_code=404, detail="研究计划尚未生成")
    with open(plan_file, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except Exception:
            raise HTTPException(status_code=500, detail="计划文件解析失败")


@app.get("/api/sessions/{session_id}/phases")
async def get_session_phases(session_id: str):
    """获取指定会话各阶段的存储内容摘要"""
    workspace = _find_workspace(session_id)
    result = {}

    # 研究计划
    plan_file = os.path.join(workspace, "03_plan.json")
    if os.path.exists(plan_file):
        with open(plan_file, 'r', encoding='utf-8') as f:
            try:
                result["plan"] = json.load(f)
            except Exception:
                pass

    # 澄清分析
    clarif_file = os.path.join(workspace, "04_clarification", "clarification.json")
    if os.path.exists(clarif_file):
        with open(clarif_file, 'r', encoding='utf-8') as f:
            try:
                result["clarification"] = json.load(f)
            except Exception:
                pass

    # 分析综合
    analysis_file = os.path.join(workspace, "05_analysis.md")
    if os.path.exists(analysis_file):
        with open(analysis_file, 'r', encoding='utf-8') as f:
            result["analysis"] = f.read()

    # 草稿列表
    drafts_dir = os.path.join(workspace, "06_drafts")
    if os.path.isdir(drafts_dir):
        drafts = []
        for fn in sorted(os.listdir(drafts_dir)):
            if fn.endswith(".md"):
                fp = os.path.join(drafts_dir, fn)
                drafts.append({
                    "name": fn,
                    "size": os.path.getsize(fp),
                    "modified": datetime.fromtimestamp(os.path.getmtime(fp)).isoformat()
                })
        result["drafts"] = drafts

    # 置信度报告
    conf_file = os.path.join(workspace, "08_verification", "confidence_report.json")
    if os.path.exists(conf_file):
        with open(conf_file, 'r', encoding='utf-8') as f:
            try:
                result["confidence_report"] = json.load(f)
            except Exception:
                pass

    return result


def _find_workspace(session_id: str) -> str:
    """按 session_id 查找工作空间路径，不存在则抛出 404"""
    ws = _find_workspace_or_none(session_id)
    if not ws:
        raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在")
    return ws


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除指定会话及其工作空间目录"""
    import shutil
    workspace = _find_workspace(session_id)
    if not os.path.isdir(workspace):
        raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在")
    shutil.rmtree(workspace)
    return {"status": "deleted", "session_id": session_id}


@app.get("/api/config")
async def get_config():
    """获取当前系统配置"""
    from config import (
        CORE_MODEL, SUPPORT_MODEL,
        MIN_IMPROVEMENT_CYCLES, MAX_IMPROVEMENT_CYCLES, QUALITY_THRESHOLD
    )
    return {
        "model": CORE_MODEL,          # 兼容旧字段
        "core_model": CORE_MODEL,
        "support_model": SUPPORT_MODEL,
        "min_improvement_cycles": MIN_IMPROVEMENT_CYCLES,
        "max_improvement_cycles": MAX_IMPROVEMENT_CYCLES,
        "quality_threshold": QUALITY_THRESHOLD,
        "max_concurrent_tasks": MAX_CONCURRENT_TASKS,
    }


@app.post("/api/config")
async def update_config(request: ConfigRequest):
    """
    更新系统配置（运行时生效）
    注意：重启后恢复默认值，如需持久化请修改 .env 文件
    """
    import config

    changes = {}

    # 核心模型
    core = request.core_model or request.model
    if core is not None:
        config.CORE_MODEL = core
        config.ORCHESTRATOR_MODEL = core
        config.PLANNER_MODEL = core
        config.RESEARCHER_MODEL = core
        config.ANALYST_MODEL = core
        config.WRITER_MODEL = core
        changes["core_model"] = core

    # 辅助模型
    if request.support_model is not None:
        config.SUPPORT_MODEL = request.support_model
        config.CRITIC_MODEL = request.support_model
        config.SOURCE_VERIFIER_MODEL = request.support_model
        config.FACT_CHECKER_MODEL = request.support_model
        config.CONCLUSION_VALIDATOR_MODEL = request.support_model
        changes["support_model"] = request.support_model

    if request.min_cycles is not None:
        if 1 <= request.min_cycles <= 10:
            config.MIN_IMPROVEMENT_CYCLES = request.min_cycles
            changes["min_cycles"] = request.min_cycles
        else:
            raise HTTPException(status_code=400, detail="min_cycles 必须在 1-10 之间")

    if request.max_cycles is not None:
        if 1 <= request.max_cycles <= 20:
            config.MAX_IMPROVEMENT_CYCLES = request.max_cycles
            changes["max_cycles"] = request.max_cycles
        else:
            raise HTTPException(status_code=400, detail="max_cycles 必须在 1-20 之间")

    if request.quality_threshold is not None:
        if 0.0 <= request.quality_threshold <= 10.0:
            config.QUALITY_THRESHOLD = request.quality_threshold
            changes["quality_threshold"] = request.quality_threshold
        else:
            raise HTTPException(status_code=400, detail="quality_threshold 必须在 0-10 之间")

    return {"updated": changes, "message": "配置已更新（重启后恢复默认值）"}


@app.post("/api/clarify")
async def start_clarify(request: ClarifyStartRequest):
    """启动研究前置澄清会话，返回 AI 第一条澄清消息"""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="研究问题不能为空")
    try:
        from agents.clarifier import ClarifierAgent
        agent = ClarifierAgent()
        result = agent.start(request.question.strip())
        clarify_id = str(uuid.uuid4())[:8]
        _clarify_sessions[clarify_id] = {
            "clarify_id": clarify_id,
            "question": request.question.strip(),
            "history": result.get("history", []),
            "summary": result.get("summary", {}),
            "turns": 1,
        }
        return {
            "clarify_id": clarify_id,
            "message": result.get("message", ""),
            "summary": result.get("summary", {}),
            "ready": result.get("ready", False),
            "confidence": result.get("confidence", 0.0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"澄清智能体启动失败：{str(e)}")


@app.post("/api/clarify/{clarify_id}/message")
async def clarify_message(clarify_id: str, request: ClarifyReplyRequest):
    """继续澄清对话"""
    session = _clarify_sessions.get(clarify_id)
    if not session:
        raise HTTPException(status_code=404, detail="澄清会话不存在")
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")
    try:
        from agents.clarifier import ClarifierAgent
        agent = ClarifierAgent()
        result = agent.reply(session["history"], request.message.strip())
        session["history"] = result.get("history", session["history"])
        session["summary"] = result.get("summary", session["summary"])
        session["turns"] += 1
        return {
            "message": result.get("message", ""),
            "summary": result.get("summary", {}),
            "ready": result.get("ready", False),
            "confidence": result.get("confidence", 0.0),
            "turns": session["turns"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"澄清对话失败：{str(e)}")


@app.post("/api/clarify/{clarify_id}/confirm")
async def confirm_clarify(clarify_id: str, request: ClarifyConfirmRequest):
    """用户确认研究需求，启动正式研究任务"""
    session = _clarify_sessions.get(clarify_id)
    if not session:
        raise HTTPException(status_code=404, detail="澄清会话不存在")

    running = _running_task_count()
    if running >= MAX_CONCURRENT_TASKS:
        raise HTTPException(
            status_code=429,
            detail=f"当前已有 {running} 个任务在运行，请等待完成后再提交。"
        )

    # 用用户编辑后的摘要（若有）覆盖
    summary = request.summary or session["summary"]

    # 将摘要拼装成富文本补充说明，传给 orchestrator
    s = summary
    parts = []
    if s.get("scope"):       parts.append(f"研究范围：{s['scope']}")
    if s.get("key_aspects"): parts.append(f"重点方面：{'、'.join(s['key_aspects'])}")
    if s.get("timeframe"):   parts.append(f"时间范围：{s['timeframe']}")
    if s.get("depth"):       parts.append(f"研究深度：{s['depth']}")
    if s.get("angle"):       parts.append(f"研究角度：{s['angle']}")
    if s.get("exclude"):     parts.append(f"排除内容：{s['exclude']}")
    if s.get("search_hints"):parts.append(f"关键搜索词：{', '.join(s['search_hints'])}")
    if request.extra_note:   parts.append(f"用户补充：{request.extra_note}")

    clarification_text = "\n".join(parts)

    # 提取意图元数据，传给 orchestrator 调整研究策略
    intent_meta = {
        "intent_type": s.get("intent_type", "info_seeking"),
        "dimensions": s.get("dimensions", {"urgency": 0.5, "specificity": 0.5, "complexity": 0.5}),
    }

    task_id = str(uuid.uuid4())[:8]
    _task_queues[task_id] = Queue()
    pause_ev = threading.Event(); pause_ev.set()
    _task_pause_events[task_id] = pause_ev
    stop_ev = threading.Event()
    _task_stop_events[task_id] = stop_ev
    _task_status[task_id] = {
        "task_id": task_id,
        "question": session["question"],
        "status": "pending",
        "progress": 0.0,
        "created_at": datetime.now().isoformat(),
        "last_observed_ts": time.time(),
        "scores": [],
        "current_cycle": 0,
        "clarify_id": clarify_id,
        "summary": summary,
        "intent_meta": intent_meta,
    }

    thread = threading.Thread(
        target=_run_research_task,
        args=(task_id, session["question"], clarification_text, None, intent_meta),
        daemon=True
    )
    thread.start()

    # 清理澄清会话（已不需要）
    _clarify_sessions.pop(clarify_id, None)

    return {
        "task_id": task_id,
        "status": "started",
        "stream_url": f"/api/research/{task_id}/stream",
        "status_url": f"/api/research/{task_id}/status",
    }


@app.get("/api/health")
async def health_check():
    """健康检查"""
    import config
    return {
        "status": "ok",
        "model": config.ORCHESTRATOR_MODEL,
        "api_key_set": bool(config.API_KEY),
        "active_tasks": len(_task_queues),
        "current_date": config.CURRENT_DATE_STR,
    }


@app.get("/api/settings")
async def get_settings():
    """获取当前 API 设置（key 脱敏显示）"""
    import config
    key = config.API_KEY
    masked = (key[:4] + '***' + key[-4:]) if len(key) > 8 else ('***' if key else '')
    return {
        "api_key_set": bool(key),
        "api_key_masked": masked,
        "base_url": config.API_BASE_URL,
        "core_model": config.CORE_MODEL,
        "support_model": config.SUPPORT_MODEL,
    }


@app.post("/api/settings")
async def update_settings(request: SettingsRequest):
    """
    更新 API 设置并持久化到 settings.json。
    立即对后续所有新任务生效（重启后也保留）。
    """
    import config
    from config import save_settings

    try:
        changes = {}

        # api_key：非空才更新，防止意外清空
        if request.api_key is not None:
            key = request.api_key.strip()
            if key:
                config.API_KEY = key
                config.ZHIPU_API_KEY = key
                config.ANTHROPIC_API_KEY = key
                changes["api_key"] = key

        # base_url：空则保持原值
        if request.base_url is not None:
            url = request.base_url.strip()
            if url:
                normalized = config.normalize_openai_base_url(url)
                config.API_BASE_URL = normalized
                config.ZHIPU_BASE_URL = normalized
                changes["base_url"] = normalized

        if request.core_model is not None:
            m = request.core_model.strip()
            if m:
                config.CORE_MODEL = m
                config.ORCHESTRATOR_MODEL = m
                config.PLANNER_MODEL = m
                config.RESEARCHER_MODEL = m
                config.ANALYST_MODEL = m
                config.WRITER_MODEL = m
                changes["core_model"] = m

        if request.support_model is not None:
            m = request.support_model.strip()
            if m:
                config.SUPPORT_MODEL = m
                config.CRITIC_MODEL = m
                config.SOURCE_VERIFIER_MODEL = m
                config.FACT_CHECKER_MODEL = m
                config.CONCLUSION_VALIDATOR_MODEL = m
                changes["support_model"] = m

        if request.min_cycles is not None:
            if 1 <= request.min_cycles <= 10:
                config.MIN_IMPROVEMENT_CYCLES = request.min_cycles
                changes["min_cycles"] = request.min_cycles
            else:
                raise HTTPException(status_code=400, detail="min_cycles 必须在 1-10 之间")

        if request.max_cycles is not None:
            if 1 <= request.max_cycles <= 20:
                config.MAX_IMPROVEMENT_CYCLES = request.max_cycles
                changes["max_cycles"] = request.max_cycles
            else:
                raise HTTPException(status_code=400, detail="max_cycles 必须在 1-20 之间")

        if request.quality_threshold is not None:
            if 0.0 <= request.quality_threshold <= 10.0:
                config.QUALITY_THRESHOLD = request.quality_threshold
                changes["quality_threshold"] = request.quality_threshold
            else:
                raise HTTPException(status_code=400, detail="quality_threshold 必须在 0-10 之间")

        save_settings(changes)
        return {"updated": list(changes.keys()), "message": "设置已保存"}

    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"保存失败：{str(e)}\n{traceback.format_exc()}")


@app.get("/api/models")
async def list_models():
    """
    从当前配置的 API 端点拉取可用模型列表（GET {base_url}/models）。
    返回模型 id 列表，供前端下拉选择。
    """
    import config
    from openai import OpenAI
    if not config.API_KEY:
        raise HTTPException(status_code=400, detail="请先配置 API Key")
    try:
        client = OpenAI(api_key=config.API_KEY, base_url=config.API_BASE_URL)
        models_page = client.models.list()
        ids = sorted(m.id for m in models_page.data)
        return {"models": ids}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"获取模型列表失败：{str(e)}")
