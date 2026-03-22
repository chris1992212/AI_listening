# -*- coding: utf-8 -*-
"""
单独测试腾讯实时 ASR（不经过 FastAPI）。

从本机或远端执行，都是：本进程用 .env 里 TENCENT_* 直连腾讯云 WebSocket ASR，
与 FastAPI / 小程序无关。

用法（在 backend 目录下）:
  python scripts/test_asr.py                    # 使用默认占位说明
  python scripts/test_asr.py /path/to/sample.m4a
  python scripts/test_asr.py ./sample.aac --sync

远端服务器上验证（与线上一致的环境）:
  1) 仓库内已有: scripts/fixtures/test_speech.m4a（也可 python scripts/generate_test_audio.py 重新生成）
  2) 阿里云 git pull 后:
       cd /path/to/backend && source .venv/bin/activate
       python scripts/test_asr.py scripts/fixtures/test_speech.m4a
  3) 或在本机一键: chmod +x scripts/test_asr_on_remote.sh
       export REMOTE=user@服务器IP
       ./scripts/test_asr_on_remote.sh

退出码: 0=识别出非空文本，3=空串，2=未配置密钥，1=缺参数/文件不存在

依赖: 同项目 requirements；需配置 .env 中 TENCENT_*；需 ffmpeg（与 meeting/chunk 相同）。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# 保证能 import app.*（无论从哪一层 cwd 执行）
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _load_env() -> None:
    from dotenv import load_dotenv

    env_path = _BACKEND / ".env"
    load_dotenv(env_path)
    if not env_path.exists():
        print(f"[warn] 未找到 {env_path}，将仅使用系统环境变量", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="测试腾讯云 ASR（transcribe）")
    parser.add_argument(
        "audio_file",
        nargs="?",
        default="",
        help="本地音频文件路径（.m4a / .aac / .wav 等，与线上一致）",
    )
    parser.add_argument("--sync", action="store_true", help="使用 transcribe_sync（默认 asyncio.run）")
    args = parser.parse_args()

    _load_env()

    from app.core.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    if not (s.TENCENT_ASR_APP_ID and s.TENCENT_SECRET_ID and s.TENCENT_SECRET_KEY):
        print(
            "[error] .env 中需配置 TENCENT_ASR_APP_ID、TENCENT_SECRET_ID、TENCENT_SECRET_KEY",
            file=sys.stderr,
        )
        return 2

    if not args.audio_file:
        print(
            "请指定音频文件，例如:\n"
            f"  cd {_BACKEND}\n"
            "  python scripts/test_asr.py scripts/fixtures/test_speech.m4a\n"
            "（仓库内固定测试音频；也可用自录 m4a）",
            file=sys.stderr,
        )
        return 1

    path = Path(args.audio_file).expanduser()
    if not path.is_file():
        print(f"[error] 文件不存在: {path}", file=sys.stderr)
        return 1

    data = path.read_bytes()
    print(f"[test] file={path} bytes={len(data)} engine={s.TENCENT_ASR_ENGINE}")

    from app.services.asr_tencent import transcribe, transcribe_sync

    if args.sync:
        out = transcribe_sync(data)
    else:
        out = asyncio.run(transcribe(data))

    print("--- result ---")
    print(out if out.strip() else "(空字符串，与线上一致则排查腾讯 ASR / ffmpeg / 密钥)")
    return 0 if out.strip() else 3


if __name__ == "__main__":
    raise SystemExit(main())
