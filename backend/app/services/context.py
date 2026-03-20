# -*- coding: utf-8 -*-
"""
会议上下文：摘要 + 近期逐字稿（按时间窗口 + 句边界截断）。
"""
import re
from typing import List, Tuple

# 句末标点（用于按句截断）
SENTENCE_END = re.compile(r"[。！？.!?]\s*")


def get_recent_context_for_llm(
    transcript_chunks: List[Tuple[float, str]],
    window_sec: int,
    max_chars: int,
    now_ts: float,
) -> str:
    """
    transcript_chunks: [(timestamp, text), ...]，按时间升序。
    取 [now_ts - window_sec, now_ts] 内的文本，再按句边界截断，总长不超过 max_chars。
    """
    start_ts = now_ts - window_sec
    parts = [t for ts, t in transcript_chunks if start_ts <= ts <= now_ts and (t or "").strip()]
    raw = "".join(parts)
    if not raw or max_chars <= 0:
        return ""

    if len(raw) <= max_chars:
        return raw.strip()

    # 在 max_chars 附近找句末
    cut = raw[: max_chars + 1]
    last_end = -1
    for m in SENTENCE_END.finditer(cut):
        last_end = m.end()
    if last_end > 0:
        return cut[:last_end].strip()
    return cut.strip()


def truncate_to_sentences(text: str, max_chars: int) -> str:
    """保留完整句子，总长不超过 max_chars。"""
    if not text or len(text) <= max_chars:
        return (text or "").strip()
    cut = text[: max_chars + 1]
    last_end = -1
    for m in SENTENCE_END.finditer(cut):
        last_end = m.end()
    if last_end > 0:
        return cut[:last_end].strip()
    return cut.strip()
