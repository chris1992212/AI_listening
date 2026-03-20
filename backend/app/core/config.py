# -*- coding: utf-8 -*-
"""配置：从环境变量读取，便于本地与部署统一。"""
import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # 腾讯云 实时语音识别
    TENCENT_ASR_APP_ID: str = ""
    TENCENT_SECRET_ID: str = ""
    TENCENT_SECRET_KEY: str = ""
    TENCENT_ASR_ENGINE: str = "16k_zh"  # 16k_zh | 16k_zh_en 等
    TENCENT_ASR_VOICE_FORMAT: int = 16  # 16=aac

    # 阿里云 大模型（DashScope 通义千问）
    ALIYUN_LLM_API_KEY: str = ""
    ALIYUN_LLM_MODEL: str = "qwen-plus"

    # 会议上下文
    MEETING_SUMMARY_INTERVAL_SEC: int = 120  # 每 N 秒更新一次会议摘要
    MEETING_RECENT_WINDOW_SEC: int = 90     # 送给 LLM 的“近期逐字稿”窗口（秒）
    MEETING_MAX_RECENT_CHARS: int = 2000    # 近期文字最大字符数（按句截断）

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
