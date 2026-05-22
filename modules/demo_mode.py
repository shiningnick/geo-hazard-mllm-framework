# -*- coding: utf-8 -*-
"""演示模式：使用本地预置结果，便于审稿人无需 API 即可复现流程。"""
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

from config import DEMO_RESULTS_PATH, DEMO_MODE


class DemoResultProvider:
    """从 sample_results.json 加载预置的指标与风险评价结果。"""

    def __init__(self, results_path: str = None):
        self.results_path = results_path or DEMO_RESULTS_PATH
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        path = Path(self.results_path)
        if not path.exists():
            return
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        # 按文件名索引
        for key, value in raw.items():
            self._cache[os.path.basename(key)] = value
            self._cache[key] = value

    def lookup(self, image_path: str) -> Optional[Dict[str, Any]]:
        name = os.path.basename(image_path)
        return self._cache.get(name)

    @staticmethod
    def is_enabled() -> bool:
        return DEMO_MODE


def split_demo_record(record: Dict[str, Any]) -> tuple:
    """将演示记录拆分为 AI 提取字段与风险评价字段。"""
    risk_keys = {"风险指数", "风险等级", "风险总分", "FHWA风险等级"}
    ai_part = {k: v for k, v in record.items() if k not in risk_keys}
    risk_part = {k: v for k, v in record.items() if k in risk_keys}
    return ai_part, risk_part
