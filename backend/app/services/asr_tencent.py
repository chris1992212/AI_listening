# -*- coding: utf-8 -*-
"""
腾讯云实时语音识别（WebSocket）。
将一段音频按 1:1 实时率发送到腾讯 ASR，收集识别文本返回。
支持 aac 格式（voice_format=16）；若为其他格式需在调用前转换。
"""
import asyncio
import base64
import hmac
import hashlib
import json
import shutil
import subprocess
import time
import uuid
from typing import Optional
from urllib.parse import quote

import websockets

from app.core.config import get_settings


def detect_voice_format(audio_bytes: bytes, filename: str = "") -> int:
    """
    根据音频字节头猜测编码/封装类型，并映射腾讯 voice_format。
    说明：微信录音通常输出 m4a/aac 容器；分片切碎会导致 4007，这里尽量减少猜错。
    """
    fn = (filename or "").lower()

    # WAV: RIFF....WAVE
    if len(audio_bytes) >= 12 and audio_bytes[0:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        return 12  # wav

    # MP4/M4A: ........ftyp....M4A/MPEG4
    # MP4 box: bytes[4:8] should be 'ftyp'
    if len(audio_bytes) >= 12 and audio_bytes[4:8] == b"ftyp":
        return 14  # m4a

    # MP3: ID3 tag or MPEG frame sync (0xFFEx)
    if fn.endswith(".mp3") or (len(audio_bytes) >= 3 and audio_bytes[0:3] == b"ID3"):
        return 8  # mp3
    if len(audio_bytes) >= 2 and audio_bytes[0] == 0xFF and (audio_bytes[1] & 0xE0) == 0xE0:
        return 8

    # AAC ADTS often begins with 0xFFF sync word.
    if fn.endswith(".aac") or (len(audio_bytes) >= 2 and audio_bytes[0] == 0xFF and (audio_bytes[1] & 0xF0) == 0xF0):
        return 16  # aac

    # fallback: use default engine voice_format
    return get_settings().TENCENT_ASR_VOICE_FORMAT


def _make_signature(secret_key: str, sign_origin: str) -> str:
    h = hmac.new(secret_key.encode("utf-8"), sign_origin.encode("utf-8"), hashlib.sha1)
    return base64.b64encode(h.digest()).decode("utf-8")


def _build_ws_url(app_id: str, secret_id: str, secret_key: str, engine: str, voice_format: int) -> str:
    timestamp = int(time.time())
    expired = timestamp + 3600
    nonce = int(time.time() * 1000) % 10**10
    voice_id = str(uuid.uuid4()).replace("-", "")[:32]

    params = {
        "engine_model_type": engine,
        "expired": expired,
        "nonce": nonce,
        "secretid": secret_id,
        "timestamp": timestamp,
        "voice_format": voice_format,
        "voice_id": voice_id,
    }
    # 签名原文：不含 wss://，按参数名字典序
    sorted_params = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    sign_origin = f"asr.cloud.tencent.com/asr/v2/{app_id}?{sorted_params}"
    signature = _make_signature(secret_key, sign_origin)
    params["signature"] = signature
    query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in sorted(params.items()))
    return f"wss://asr.cloud.tencent.com/asr/v2/{app_id}?{query}"


def _convert_to_pcm_s16le_16k_mono(audio_bytes: bytes) -> bytes:
    """
    将任意音频容器/编码转换为 Tencent 实时 ASR 期望的 PCM16k 单声道 s16le。
    需要本机安装 ffmpeg。
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg 未安装或未加入 PATH")

    # 使用 pipe:0/pipe:1 避免落盘，减少 IO；输出即 PCM 二进制
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "s16le",
        "pipe:1",
    ]
    proc = subprocess.run(
        cmd,
        input=audio_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 转码失败: {proc.stderr.decode('utf-8', errors='ignore')[:300]}")
    return proc.stdout


async def transcribe(audio_bytes: bytes, voice_format_override: Optional[int] = None) -> str:
    """
    将一段音频（aac）发送到腾讯云实时识别，返回识别得到的文本（多句用空格或标点连接）。
    """
    settings = get_settings()
    if not settings.TENCENT_ASR_APP_ID or not settings.TENCENT_SECRET_ID or not settings.TENCENT_SECRET_KEY:
        return ""

    # 对接腾讯实时 ASR 的最稳策略：先统一转成 PCM16k 单声道 s16le，再走 voice_format=1。
    detected_voice_format = voice_format_override if voice_format_override is not None else settings.TENCENT_ASR_VOICE_FORMAT
    if detected_voice_format != 1:
        try:
            audio_bytes = await asyncio.to_thread(_convert_to_pcm_s16le_16k_mono, audio_bytes)
        except Exception as e:
            print(f"[ASR] ffmpeg convert error: {e}")
            return ""

    voice_format = 1  # PCM

    url = _build_ws_url(
        settings.TENCENT_ASR_APP_ID,
        settings.TENCENT_SECRET_ID,
        settings.TENCENT_SECRET_KEY,
        settings.TENCENT_ASR_ENGINE,
        voice_format,
    )

    # PCM16k mono s16le：16000 samples/s * 2 bytes/sample = 32000 B/s => 200ms=6400B
    bytes_per_sec = 16000 * 2
    duration_sec = max(1.0, len(audio_bytes) / bytes_per_sec)
    chunk_size = 6400
    num_chunks = max(1, (len(audio_bytes) + chunk_size - 1) // chunk_size)
    send_interval = 0.2

    print(
        f"[ASR] audio_bytes={len(audio_bytes)} est_dur={duration_sec:.2f}s "
        + f"chunks={num_chunks} chunk_size={chunk_size} send_interval={send_interval:.3f}s "
        + f"engine={settings.TENCENT_ASR_ENGINE} voice_format={voice_format}"
    )

    results: list[str] = []
    last_error: dict | None = None

    async def send_audio(ws):
        for i in range(0, len(audio_bytes), chunk_size):
            chunk = audio_bytes[i : i + chunk_size]
            if chunk:
                await ws.send(chunk)
            await asyncio.sleep(send_interval)
        await ws.send(json.dumps({"type": "end"}))

    async def recv_loop(ws):
        nonlocal results, last_error
        try:
            async for msg in ws:
                if isinstance(msg, str):
                    data = json.loads(msg)
                    if data.get("code") != 0:
                        last_error = data
                        print(f"[ASR] recv nonzero code={data.get('code')} message={data.get('message')}")
                        try:
                            await ws.close()
                        except Exception:
                            pass
                        return
                    if data.get("final") == 1:
                        return
                    res = data.get("result")
                    if res and isinstance(res, dict):
                        text = (res.get("voice_text_str") or "").strip()
                        if text and res.get("slice_type") == 2:
                            print(f"[ASR] final slice_type=2 text={text}")
                            results.append(text)
        except Exception:
            pass

    try:
        async with websockets.connect(
            url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
            open_timeout=10,
        ) as ws:
            # 先收一条握手响应
            first = await ws.recv()
            first_data = json.loads(first)
            print(f"[ASR] handshake code={first_data.get('code')} message={first_data.get('message')}")
            if first_data.get("code") != 0:
                return ""
            recv_task = asyncio.create_task(recv_loop(ws))
            await send_audio(ws)
            await asyncio.wait_for(recv_task, timeout=duration_sec + 15)
    except Exception as e:
        print(f"[ASR] connect/stream error: {e}")
        return ""

    # 识别失败时返回空字符串，由上层决定是否重试/降级
    if not results and last_error:
        print(f"[ASR] no results, last_error={last_error}")
    return "".join(results) if results else ""


def transcribe_sync(audio_bytes: bytes) -> str:
    """同步封装，供非 async 环境或测试用。"""
    return asyncio.run(transcribe(audio_bytes))


if __name__ == "__main__":
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="Test Tencent ASR: transcribe a local aac file.")
    parser.add_argument("file", nargs="?", default="", help="Path to .aac file")
    parser.add_argument("--sync", action="store_true", help="Use sync wrapper")
    args = parser.parse_args()
    if not args.file:
        print("Usage: python -m app.services.asr_tencent <file.aac>", file=sys.stderr)
        sys.exit(1)
    with open(args.file, "rb") as f:
        data = f.read()
    fn = transcribe_sync if args.sync else lambda b: asyncio.run(transcribe(b))
    out = fn(data)
    print("transcript:", out)
