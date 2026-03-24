# -*- coding: utf-8 -*-
"""
会议状态内存存储（MVP 单机可用）。后续可替换为 Redis/DB。
"""
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

# meeting_id -> MeetingState
_meetings: Dict[str, "MeetingState"] = {}


class MeetingState:
    def __init__(
        self,
        meeting_id: str,
        topic: str,
        goal_type: str,
        goal_desc: str,
        role: str = "参会人",
        assistant_only: bool = False,
    ):
        self.meeting_id = meeting_id
        self.topic = topic
        self.goal_type = goal_type
        self.goal_desc = goal_desc
        self.role = role
        # True=会议助手模式（仅录音识别+会后总结，不做实时发言提示）
        self.assistant_only = assistant_only
        self.started_at = time.time()
        self.ended_at: Optional[float] = None
        # (timestamp, text) 按时间顺序
        self.transcript: List[Tuple[float, str]] = []
        # 会议摘要（周期性由 LLM 更新或简单拼接）
        self.summary: str = ""
        self.summary_updated_at: float = 0.0
        # 当前建议
        self.advice: Dict[str, Any] = {
            "should_speak": False,
            "priority": "low",
            "sample_utterance": "",
            "reason": "",
        }
        self.advice_updated_at: float = 0.0


def create_meeting(
    topic: str,
    goal_type: str,
    goal_desc: str,
    role: str = "参会人",
    assistant_only: bool = False,
) -> str:
    meeting_id = str(uuid.uuid4())[:16]
    _meetings[meeting_id] = MeetingState(
        meeting_id=meeting_id,
        topic=topic,
        goal_type=goal_type,
        goal_desc=goal_desc,
        role=role,
        assistant_only=assistant_only,
    )
    return meeting_id


def get_meeting(meeting_id: str) -> Optional[MeetingState]:
    return _meetings.get(meeting_id)


def append_transcript(meeting_id: str, text: str) -> None:
    m = _meetings.get(meeting_id)
    if not m or m.ended_at:
        return
    if (text or "").strip():
        m.transcript.append((time.time(), text.strip()))


def update_advice(meeting_id: str, advice: Dict[str, Any]) -> None:
    m = _meetings.get(meeting_id)
    if not m or m.ended_at:
        return
    m.advice = advice
    m.advice_updated_at = time.time()


def update_summary(meeting_id: str, summary: str) -> None:
    m = _meetings.get(meeting_id)
    if not m or m.ended_at:
        return
    m.summary = summary
    m.summary_updated_at = time.time()


def end_meeting(meeting_id: str) -> None:
    m = _meetings.get(meeting_id)
    if m:
        m.ended_at = time.time()
