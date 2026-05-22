# -*- coding: utf-8 -*-
"""
系统配置文件（投稿代码包）
API 密钥请通过环境变量配置，勿提交到公开仓库。
"""
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

INPUT_DIR = os.path.join(PROJECT_ROOT, "input")
os.makedirs(INPUT_DIR, exist_ok=True)

DEMO_DATA_DIR = os.path.join(PROJECT_ROOT, "demo_data")
DEMO_IMAGES_DIR = os.path.join(DEMO_DATA_DIR, "images")

# 从环境变量读取 API Key（复制 config.example.py 后设置）
def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


MODEL_CONFIGS = {
    "openai": {
        "api_key": _env("OPENAI_API_KEY"),
        "base_url": _env("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "models": ["gpt-4o-mini", "gpt-4o"],
        "timeout": 300,
        "api_type": "openai",
    },
    "gemini": {
        "api_key": _env("GEMINI_API_KEY", _env("OPENAI_API_KEY")),
        "base_url": _env("GEMINI_BASE_URL", _env("OPENAI_BASE_URL", "https://api.openai.com/v1")),
        "models": ["gemini-2.0-flash"],
        "timeout": 300,
        "api_type": "openai",
    },
    "anthropic": {
        "api_key": _env("ANTHROPIC_API_KEY", _env("OPENAI_API_KEY")),
        "base_url": _env("ANTHROPIC_BASE_URL", _env("OPENAI_BASE_URL", "https://api.openai.com/v1")),
        "models": ["claude-3-5-haiku-latest"],
        "timeout": 300,
        "api_type": "openai",
    },
    "grok": {
        "api_key": _env("GROK_API_KEY", _env("OPENAI_API_KEY")),
        "base_url": _env("GROK_BASE_URL", _env("OPENAI_BASE_URL", "https://api.openai.com/v1")),
        "models": ["grok-2-vision"],
        "timeout": 300,
        "api_type": "openai",
    },
    "qwen": {
        "api_key": _env("QWEN_API_KEY", _env("OPENAI_API_KEY")),
        "base_url": _env("QWEN_BASE_URL", _env("OPENAI_BASE_URL", "https://api.openai.com/v1")),
        "models": ["qwen-vl-plus"],
        "timeout": 300,
        "api_type": "openai",
    },
}

DEFAULT_MODEL_PROVIDER = os.environ.get("DEFAULT_MODEL_PROVIDER", "openai")
DEFAULT_MODEL_NAME = os.environ.get("DEFAULT_MODEL_NAME", "gpt-4o-mini")

EXCEL_OUTPUT_PATH = os.path.join(OUTPUT_DIR, "地质灾害调查结果.xlsx")
EXCEL_SHEET_NAME = "调查数据"
RISK_EXCEL_OUTPUT_PATH = os.path.join(OUTPUT_DIR, "地质灾害风险评价结果.xlsx")

EXTERNAL_DATA_CONFIG = {
    "precipitation_api": {"url": "", "api_key": ""},
    "earthquake_api": {"url": "", "api_key": ""},
    "slope_api": {"url": "", "api_key": ""},
}

# 演示模式：使用本地预置结果，无需调用大模型 API
DEMO_MODE = os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes")
DEMO_RESULTS_PATH = os.path.join(DEMO_DATA_DIR, "sample_results.json")
