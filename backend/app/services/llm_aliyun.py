# -*- coding: utf-8 -*-
"""
阿里云大模型（DashScope 通义千问）封装。
根据会议摘要 + 近期逐字稿 + 用户目标，返回是否建议发言及建议话术。
"""
import json
import re
import urllib.request
from typing import Any

from app.core.config import get_settings
from app.services.context import truncate_to_sentences


SYSTEM_PROMPT = """你是一个帮助内向职场人士的会议教练。用户会在会议中看到你给出的"是否该发言"以及"建议说什么"。
请根据【会议摘要】和【近期讨论内容】，结合用户的【会议目标】，判断当前是否适合用户介入发言。
若适合，给出简短、可直接照着说的一两句话（问题或陈述），并说明这句话如何帮助达成用户目标。
必须只输出一段合法 JSON，不要其他解释。JSON 格式如下：
{"summary":"大约1-2句话的会议简版总结（不超过120字）","should_speak": true|false, "priority": "low"|"medium"|"high", "sample_utterance": "建议说的内容；若不必说则空字符串", "reason": "一句话理由"}
"""

DASHSCOPE_GENERATION_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"

FINAL_SYSTEM_PROMPT = """你是一个帮助内向职场人士的会议教练。现在会给你一份会议的逐字稿（转写文本）。
请你基于【整体会议内容】总结会议，并为“用户的角色 + 用户的目的”输出可执行的发言策略。

要求：必须只输出一段合法 JSON，不要其他解释。JSON 必须包含以下字段：
{
  "overall_summary": "总体总结（不超过200字）",
  "key_points": ["关键点1","关键点2","..."],
  "your_role_goal_insight": "站在用户角色与目的视角，对会议的关键观察（不超过200字）",
  "better_speaking": [
    {"when":"适合发言的时机","what_to_say":"建议话术（可直接照读）","why":"为什么要说/如何帮助达成目的"}
  ]
}

禁止输出非 JSON 内容。key_points 至少 3 条；better_speaking 至少 3 条。
"""


def _extract_content_from_dashscope_response(data: dict[str, Any]) -> str:
    out = data.get("output") or {}
    if isinstance(out, dict):
        # 常见结构：output.choices[0].message.content
        choices = out.get("choices")
        if isinstance(choices, list) and choices:
            for c in choices:
                if not isinstance(c, dict):
                    continue
                msg = c.get("message")
                if isinstance(msg, dict) and msg.get("content"):
                    return msg.get("content") or ""
                # 兜底：text/content
                if c.get("text"):
                    return c.get("text") or ""
                if c.get("content"):
                    return c.get("content") or ""

        # 另一些结构：output.text
        if out.get("text"):
            return out.get("text") or ""
        if isinstance(out.get("message"), dict) and out["message"].get("content"):
            return out["message"].get("content") or ""

    # 兜底：data 本身可能直接是 message
    if isinstance(data.get("message"), dict) and data["message"].get("content"):
        return data["message"].get("content") or ""
    return ""


def _extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\\s*", "", s)
        s = re.sub(r"```\\s*$", "", s).strip()

    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        s = s[start : end + 1]

    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # 兼容少数模型输出 True/False
        s2 = s.replace("True", "true").replace("False", "false")
        try:
            return json.loads(s2)
        except json.JSONDecodeError:
            return None


def _call_dashscope(messages: list[dict[str, str]], model: str, api_key: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "input": {"messages": messages},
        "parameters": {"max_tokens": 256, "temperature": 0.2},
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        DASHSCOPE_GENERATION_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8", errors="strict")
        data = json.loads(raw)
        # 打印结构信息，方便排查 response schema
        try:
            out = data.get("output") or {}
            print(f"[LLM] raw keys={list(data.keys())} output_keys={list(out.keys()) if isinstance(out, dict) else type(out)}")
        except Exception:
            pass
        return data


def get_meeting_advice(
    meeting_summary: str,
    recent_transcript: str,
    goal_type: str,
    goal_desc: str,
    role: str = "参会人",
) -> dict[str, Any]:
    """
    调用大模型，返回 { should_speak, priority, sample_utterance, reason }。
    """
    settings = get_settings()
    if not settings.ALIYUN_LLM_API_KEY:
        return {
            "should_speak": False,
            "priority": "low",
            "sample_utterance": "",
            "reason": "未配置大模型",
        }

    user_content = f"""【会议摘要】
{meeting_summary or "（暂无）"}

【近期讨论内容】
{recent_transcript or "（暂无）"}

【用户会议目标】
类型：{goal_type}
具体：{goal_desc}
角色：{role}

请输出 JSON：should_speak, priority, sample_utterance, reason。"""

    try:
        data = _call_dashscope(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            model=settings.ALIYUN_LLM_MODEL,
            api_key=settings.ALIYUN_LLM_API_KEY,
        )
    except Exception as e:
        return {
            "should_speak": False,
            "priority": "low",
            "sample_utterance": "",
            "reason": f"调用异常: {e}",
        }

    text = _extract_content_from_dashscope_response(data)
    print(f"[LLM] extracted content len={len(text or '')} preview={(text or '')[:160]}")
    if not text:
        return {
            "should_speak": False,
            "priority": "low",
            "sample_utterance": "",
            "reason": "模型无有效返回",
        }

    out = _extract_json(text)
    print(f"[LLM] parsed json={out}")
    if not out:
        return {
            "should_speak": False,
            "priority": "low",
            "sample_utterance": "",
            "reason": "模型返回非 JSON",
        }

    return {
        "summary": (out.get("summary") or "").strip(),
        "should_speak": bool(out.get("should_speak", False)),
        "priority": out.get("priority") or "low",
        "sample_utterance": (out.get("sample_utterance") or "").strip(),
        "reason": (out.get("reason") or "").strip(),
    }


def get_final_meeting_report(
    meeting_transcript: str,
    topic: str,
    goal_type: str,
    goal_desc: str,
    role: str = "参会人",
) -> dict[str, Any]:
    """
    会后复盘：总体总结 + 关键点 + 你的角色/目的视角 + 更好的发言建议。
    """
    settings = get_settings()
    if not settings.ALIYUN_LLM_API_KEY:
        return {
            "overall_summary": "",
            "key_points": [],
            "your_role_goal_insight": "",
            "better_speaking": [],
        }

    transcript = truncate_to_sentences(meeting_transcript or "", 8000)
    user_content = f"""【会议主题】
{topic or "（暂无）"}

【整体会议内容（转写）】
{transcript or "（暂无）"}

【用户会议目标】
类型：{goal_type}
具体：{goal_desc}
角色：{role}
"""

    data = None
    try:
        data = _call_dashscope(
            messages=[
                {"role": "system", "content": FINAL_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            model=settings.ALIYUN_LLM_MODEL,
            api_key=settings.ALIYUN_LLM_API_KEY,
        )
    except Exception as e:
        return {
            "overall_summary": "",
            "key_points": [],
            "your_role_goal_insight": "",
            "better_speaking": [],
            "reason": f"调用异常: {e}",
        }

    text = _extract_content_from_dashscope_response(data)
    if not text:
        # fallback：给一个很粗的兜底报告
        overall = truncate_to_sentences(transcript, 200)
        return {
            "overall_summary": overall,
            "key_points": [],
            "your_role_goal_insight": f"用户目标：{goal_desc or goal_type}。",
            "better_speaking": [
                {"when": "合适的结论/决策点出现后", "what_to_say": "我想补充一下：为了达成我们的目标，我建议关注 A 和 B，并明确下一步的负责人和时间。", "why": "让讨论聚焦到可执行的下一步，更容易达成你的目的。"},
            ],
        }

    out = _extract_json(text)
    if not out:
        overall = truncate_to_sentences(transcript, 200)
        return {
            "overall_summary": overall,
            "key_points": [],
            "your_role_goal_insight": f"用户目标：{goal_desc or goal_type}。",
            "better_speaking": [
                {"when": "会议中段的轮到发言环节", "what_to_say": "我理解我们现在主要在讨论 X。为了更快推进，我建议先确认 Y 的边界条件。", "why": "用“澄清+推进”的方式不抢话但能推动流程。"},
            ],
        }

    # 归一化字段类型，避免小概率模型输出不符合预期导致前端渲染异常
    key_points = out.get("key_points") or []
    if not isinstance(key_points, list):
        key_points = [str(key_points)]

    better = out.get("better_speaking") or []
    if not isinstance(better, list):
        better = [better]

    # 每条确保字段存在
    normalized_better = []
    for b in better:
        if not isinstance(b, dict):
            continue
        normalized_better.append(
            {
                "when": str(b.get("when") or "").strip(),
                "what_to_say": str(b.get("what_to_say") or "").strip(),
                "why": str(b.get("why") or "").strip(),
            }
        )

    return {
        "overall_summary": str(out.get("overall_summary") or "").strip(),
        "key_points": [str(x).strip() for x in key_points if str(x).strip()],
        "your_role_goal_insight": str(out.get("your_role_goal_insight") or "").strip(),
        "better_speaking": normalized_better,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", default="产品需求评审，正在讨论下季度优先级。")
    parser.add_argument("--recent", default="那后端接口最晚下周要定下来，前端才能排期。")
    parser.add_argument("--goal-type", default="展示能力")
    parser.add_argument("--goal-desc", default="希望让领导看到我对接口设计的思考。")
    args = parser.parse_args()
    r = get_meeting_advice(
        meeting_summary=args.summary,
        recent_transcript=args.recent,
        goal_type=args.goal_type,
        goal_desc=args.goal_desc,
    )
    print(json.dumps(r, ensure_ascii=False, indent=2))
