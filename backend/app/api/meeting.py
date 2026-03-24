# -*- coding: utf-8 -*-
"""
会议相关 API：start / chunk / status / end。
"""
import asyncio
import time
from typing import Optional

from pydantic import BaseModel
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.core.config import get_settings
from app.models.store import (
    create_meeting,
    get_meeting,
    append_transcript,
    update_advice,
    update_summary,
    end_meeting,
)
from app.services.asr_tencent import transcribe as asr_transcribe, detect_voice_format
from app.services.llm_aliyun import get_meeting_advice, get_final_meeting_report
from app.services.context import get_recent_context_for_llm, truncate_to_sentences

router = APIRouter(prefix="/api/meeting", tags=["meeting"])


class MeetingStartBody(BaseModel):
    topic: str
    goal_type: str = "展示能力"
    goal_desc: str = ""
    role: str = "参会人"
    assistant_only: bool = False


@router.post("/start")
def meeting_start(body: MeetingStartBody):
    """创建会议，返回 meeting_id。请求体 JSON: topic, goal_type?, goal_desc?, role?"""
    meeting_id = create_meeting(
        topic=body.topic,
        goal_type=body.goal_type,
        goal_desc=body.goal_desc or body.topic,
        role=body.role,
        assistant_only=body.assistant_only,
    )
    return {"meeting_id": meeting_id, "assistant_only": body.assistant_only}


_advice_task_running: dict[str, bool] = {}


async def _refresh_advice_in_background(meeting_id: str) -> None:
    """后台刷新实时建议，避免阻塞 chunk 返回。"""
    if _advice_task_running.get(meeting_id):
        return
    _advice_task_running[meeting_id] = True
    try:
        meeting = get_meeting(meeting_id)
        if not meeting or meeting.ended_at or meeting.assistant_only:
            return
        settings = get_settings()
        now_ts = time.time()
        recent = get_recent_context_for_llm(
            meeting.transcript,
            window_sec=settings.MEETING_RECENT_WINDOW_SEC,
            max_chars=settings.MEETING_MAX_RECENT_CHARS,
            now_ts=now_ts,
        )
        summary_sec = settings.MEETING_SUMMARY_INTERVAL_SEC
        summary_parts = [t for ts, t in meeting.transcript if now_ts - summary_sec <= ts <= now_ts]
        summary = truncate_to_sentences("".join(summary_parts), 1500)
        if summary:
            update_summary(meeting_id, summary)
        if not (recent or summary).strip():
            return
        advice = await asyncio.to_thread(
            get_meeting_advice,
            meeting.summary or summary,
            recent,
            meeting.goal_type,
            meeting.goal_desc,
            meeting.role,
        )
        if advice.get("summary"):
            update_summary(meeting_id, advice["summary"])
        update_advice(meeting_id, advice)
    except Exception as e:
        print(f"[chunk] advice background error: {e}")
    finally:
        _advice_task_running[meeting_id] = False


@router.post("/chunk")
async def meeting_upload_chunk(
    meeting_id: str = Form(...),
    audio: UploadFile = File(...),
):
    """上传一段录音：腾讯 ASR 转写 + 阿里云大模型给出发言建议。"""
    meeting = get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="meeting not found")
    if meeting.ended_at:
        raise HTTPException(status_code=400, detail="meeting already ended")

    body = await audio.read()
    if not body:
        return {"ok": True, "text": ""}

    # 1) 腾讯云实时识别
    # 根据音频字节头/文件名推断 voice_format，提高“音频解码失败(4007)”成功率
    filename = (audio.filename or "").lower()
    voice_format_override = detect_voice_format(body, filename=filename)

    print(
        f"[ASR] detect voice_format={voice_format_override} filename={filename} "
        f"audio_len={len(body)} head={body[:16].hex()}"
    )
    text = await asr_transcribe(body, voice_format_override=voice_format_override)
    # 云端排查：界面无输出时先看 text_len 是否为 0（ASR 空则前端也不会有转写）
    preview = (text or "")[:120].replace("\n", " ")
    print(f"[chunk] meeting_id={meeting_id} text_len={len(text or '')} text_preview={preview!r}")
    if text:
        append_transcript(meeting_id, text)

    # 2) 更新简版会议摘要（不依赖 LLM，确保助手模式也能快速看到“聊了什么”）
    settings = get_settings()
    now_ts = time.time()
    summary_sec = settings.MEETING_SUMMARY_INTERVAL_SEC
    summary_parts = [t for ts, t in meeting.transcript if now_ts - summary_sec <= ts <= now_ts]
    summary = truncate_to_sentences("".join(summary_parts), 1500)
    if summary:
        update_summary(meeting_id, summary)

    # 3) 普通模式下，实时建议改为后台异步更新，减少 chunk 阻塞；助手模式不做实时建议
    if not meeting.assistant_only:
        should_refresh = (time.time() - meeting.advice_updated_at) >= 6
        if should_refresh:
            asyncio.create_task(_refresh_advice_in_background(meeting_id))

    return {"ok": True, "text": text or ""}


@router.get("/status")
def meeting_status(meeting_id: str):
    """轮询：返回当前会议状态与建议（信号灯 + 话术）。"""
    meeting = get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="meeting not found")

    # 近期转写（最近几条，供前端展示）
    recent_lines = [t for _, t in meeting.transcript[-10:]]
    return {
        "topic": meeting.topic,
        "assistant_only": meeting.assistant_only,
        "summary": meeting.summary,
        "recent_lines": recent_lines,
        "should_speak": meeting.advice["should_speak"],
        "priority": meeting.advice["priority"],
        "sample_utterance": meeting.advice["sample_utterance"],
        "reason": meeting.advice["reason"],
    }


@router.post("/end")
def meeting_end(meeting_id: str = Query(..., alias="meeting_id")):
    """结束会议，生成会后复盘报告。请求: POST /api/meeting/end?meeting_id=xxx"""
    meeting = get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="meeting not found")
    end_meeting(meeting_id)
    full_text = " ".join(t for _, t in meeting.transcript)
    report = get_final_meeting_report(
        meeting_transcript=full_text,
        topic=meeting.topic,
        goal_type=meeting.goal_type,
        goal_desc=meeting.goal_desc,
        role=meeting.role,
    )
    return {
        "ok": True,
        "assistant_only": meeting.assistant_only,
        "full_transcript": full_text,
        "final_report": report,
        "final_summary": report.get("overall_summary") or meeting.summary or truncate_to_sentences(full_text, 2000),
    }
