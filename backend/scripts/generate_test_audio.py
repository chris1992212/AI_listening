# -*- coding: utf-8 -*-
"""
生成一段测试音频，用于 ASR（不依赖你手动录音）。

优先级:
  1) macOS: `say`（自动挑选 zh_CN/zh_TW/zh_HK 等中文音色）+ ffmpeg → m4a
  2) Linux: `espeak-ng` 中文 + ffmpeg → m4a
  3) 任意平台: 仅 ffmpeg 生成 3 秒正弦波 m4a（**无语音内容**，ASR 多为空，只用于测通文件/接口）

用法:
  cd backend && python scripts/generate_test_audio.py
  python scripts/generate_test_audio.py -o scripts/fixtures/test_speech.m4a
  python scripts/generate_test_audio.py -o tmp/x.m4a --tone-only

依赖: ffmpeg；中文语音另需 macOS `say` 或 Linux `espeak-ng`。
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), file=sys.stderr)
    subprocess.run(cmd, check=True)


def _ffmpeg_to_m4a(src: Path, dst: Path) -> None:
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(src),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "aac",
            "-b:a",
            "64k",
            str(dst),
        ]
    )


def _macos_list_voices() -> str:
    r = subprocess.run(
        ["say", "-v", "?"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr or "say -v ? failed")
    return r.stdout


def _macos_pick_chinese_voice() -> str | None:
    """返回 say -v 里的音色名（第一列），优先普通话/国语/粤语。"""
    text = _macos_list_voices()
    preferred: list[tuple[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # 形如: Ting-Ting           zh_CN    # ...
        m = re.match(r"^(\S+)\s+", line)
        if not m:
            continue
        name = m.group(1)
        rest = line[len(name) :].strip()
        if "zh_CN" in rest or "zh_TW" in rest or "zh_HK" in rest:
            preferred.append((name, rest))
    if not preferred:
        return None
    # 优先 zh_CN 普通话
    for name, rest in preferred:
        if "zh_CN" in rest:
            return name
    return preferred[0][0]


def generate_macos_say(text: str, out: Path) -> None:
    if not shutil.which("say"):
        raise RuntimeError("未找到 say（应为 macOS）")
    if not shutil.which("ffmpeg"):
        raise RuntimeError("请先安装 ffmpeg: brew install ffmpeg")

    voice = _macos_pick_chinese_voice()
    with tempfile.TemporaryDirectory() as td:
        aiff = Path(td) / "speech.aiff"
        if voice:
            print(f"[info] 使用系统语音: {voice}", file=sys.stderr)
            _run(["say", "-v", voice, text, "-o", str(aiff)])
        else:
            print(
                "[warn] 未检测到中文语音包，改用英文 Samantha（16k_zh 引擎可能对英文识别弱）",
                file=sys.stderr,
            )
            _run(["say", "-v", "Samantha", "Hello, this is a speech recognition test.", "-o", str(aiff)])
        _ffmpeg_to_m4a(aiff, out)


def generate_linux_espeak(text: str, out: Path) -> None:
    if not shutil.which("espeak-ng") and not shutil.which("espeak"):
        raise RuntimeError("请安装: sudo apt install espeak-ng ffmpeg")
    if not shutil.which("ffmpeg"):
        raise RuntimeError("请先安装 ffmpeg")

    espeak = "espeak-ng" if shutil.which("espeak-ng") else "espeak"
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "speech.wav"
        _run([espeak, "-v", "zh", text, "-w", str(wav)])
        _ffmpeg_to_m4a(wav, out)


def generate_tone_only_m4a(out: Path, seconds: float = 3.0) -> None:
    """无 TTS 时生成一段 1kHz 正弦波（非语音，ASR 通常返回空）。"""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("请先安装 ffmpeg")
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=1000:sample_rate=16000:duration={seconds}",
            "-ac",
            "1",
            "-c:a",
            "aac",
            "-b:a",
            "64k",
            str(out),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="生成用于 ASR 测试的 m4a")
    parser.add_argument(
        "-o",
        "--output",
        default=str(_BACKEND / "scripts" / "fixtures" / "test_speech.m4a"),
        help="输出路径（默认 backend/scripts/fixtures/test_speech.m4a，可提交 Git）",
    )
    parser.add_argument(
        "-t",
        "--text",
        default="你好，这是语音识别测试，一二三四五。",
        help="中文朗读内容（需系统有中文 TTS）",
    )
    parser.add_argument(
        "--tone-only",
        action="store_true",
        help="不调用 say/espeak，仅用 ffmpeg 生成正弦波（测通文件用，ASR 多为空）",
    )
    args = parser.parse_args()

    out = Path(args.output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    import platform

    system = platform.system()
    try:
        if args.tone_only:
            generate_tone_only_m4a(out)
        elif system == "Darwin":
            generate_macos_say(args.text, out)
        elif system == "Linux":
            generate_linux_espeak(args.text, out)
        else:
            print(
                f"[warn] 系统 {system} 无内置 TTS，改用 --tone-only 正弦波",
                file=sys.stderr,
            )
            generate_tone_only_m4a(out)
    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1

    print(f"[ok] 已生成: {out} ({out.stat().st_size} bytes)")
    print(f"     测 ASR:   python scripts/test_asr.py {out}")
    if args.tone_only or system not in ("Darwin", "Linux"):
        print("     （正弦波无语音，腾讯云 ASR 多半返回空，仅验证链路）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
