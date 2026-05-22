# -*- coding: utf-8 -*-
"""
演示脚本：无需 API Key，使用预置结果跑通完整流程。

用法：
  set DEMO_MODE=1          # Windows CMD
  $env:DEMO_MODE="1"       # PowerShell
  python demo_run.py
"""
import os
import sys
from pathlib import Path

# 强制启用演示模式
os.environ["DEMO_MODE"] = "1"

from modules.system_scheduler import SystemScheduler
from config import DEMO_IMAGES_DIR, OUTPUT_DIR


def main():
    demo_dir = Path(DEMO_IMAGES_DIR)
    images = sorted(demo_dir.glob("*.jpg")) + sorted(demo_dir.glob("*.png"))
    if not images:
        print(f"未找到演示图片: {demo_dir}")
        sys.exit(1)

    print("=" * 60)
    print("地质灾害风险识别 — 演示模式")
    print(f"演示图片: {len(images)} 张")
    print(f"输出目录: {OUTPUT_DIR}")
    print("=" * 60)

    scheduler = SystemScheduler()
    results = scheduler.process_batch_images(
        [str(p) for p in images],
        enable_risk_assessment=True,
        enable_external_data=False,
    )

    print("\n处理摘要:")
    for r in results:
        if "error" in r:
            print(f"  [失败] {r.get('image_path', '?')}: {r['error']}")
        else:
            print(
                f"  {r.get('编号', '?')} | {r.get('风险类型', '?')} | "
                f"规模: {r.get('规模等级', '?')} | 风险: {r.get('风险等级', '未评价')}"
            )
    print(f"\nExcel 已写入: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
