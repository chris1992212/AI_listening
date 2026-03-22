#!/usr/bin/env bash
# 在本机生成好 test_speech.m4a 后，上传到远端服务器并执行 test_asr.py，
# 用远端同一套 .env 直连「腾讯云实时语音识别」，验证与线上一致。
#
# 用法:
#   chmod +x scripts/test_asr_on_remote.sh
#   export REMOTE=root@你的服务器IP
#   export REMOTE_DIR=/opt/AI_listening/backend   # 远端 backend 根目录
#   ./scripts/test_asr_on_remote.sh             # 默认上传 backend/scripts/fixtures/test_speech.m4a
#   ./scripts/test_asr_on_remote.sh /path/to/x.m4a
#
# 前提: 本机已 ssh 免密或能交互输入密码；远端已部署项目、有 .venv、.env 里 TENCENT_*、已装 ffmpeg。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOCAL_M4A="${1:-$BACKEND_DIR/scripts/fixtures/test_speech.m4a}"

REMOTE="${REMOTE:-}"
REMOTE_DIR="${REMOTE_DIR:-/opt/AI_listening/backend}"

if [[ -z "$REMOTE" ]]; then
  echo "请设置远端 SSH，例如:" >&2
  echo "  export REMOTE=ubuntu@8.162.10.206" >&2
  echo "  export REMOTE_DIR=/opt/AI_listening/backend" >&2
  echo "  $0" >&2
  exit 1
fi

if [[ ! -f "$LOCAL_M4A" ]]; then
  echo "找不到音频: $LOCAL_M4A" >&2
  echo "请先生成: cd $BACKEND_DIR && python scripts/generate_test_audio.py" >&2
  exit 1
fi

REMOTE_FIXTURE="$REMOTE_DIR/scripts/fixtures/test_speech.m4a"
echo "==> 上传: $LOCAL_M4A -> $REMOTE:$REMOTE_FIXTURE"
ssh "$REMOTE" "mkdir -p '$REMOTE_DIR/scripts/fixtures'"
scp "$LOCAL_M4A" "$REMOTE:$REMOTE_FIXTURE"

echo "==> 远端执行 ASR 测试（使用服务器上的 .env）"
ssh "$REMOTE" "cd '$REMOTE_DIR' && if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi && python scripts/test_asr.py scripts/fixtures/test_speech.m4a"

echo "==> 完成。退出码含义见 test_asr.py：0=有字，3=空串"
