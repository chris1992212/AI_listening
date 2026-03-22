# ASR 测试用音频

- **`test_speech.m4a`**：由 `scripts/generate_test_audio.py` 在本机（macOS）生成的**中文 TTS 测试音频**，约 40KB，用于 `scripts/test_asr.py` 验证腾讯云实时语音识别。
- 可提交到 Git，便于在阿里云等环境 `git pull` 后直接运行：

```bash
cd backend
source .venv/bin/activate   # 若有
python scripts/test_asr.py scripts/fixtures/test_speech.m4a
```

如需重新生成（会覆盖本文件，需在 macOS 或有 `espeak-ng` 的 Linux 上执行）：

```bash
python scripts/generate_test_audio.py -o scripts/fixtures/test_speech.m4a
```
