# -*- coding: utf-8 -*-
"""
地质灾害调查系统 - 主程序入口
"""
import argparse
import sys
from pathlib import Path
from modules.system_scheduler import SystemScheduler
from config import DEFAULT_MODEL_PROVIDER, DEFAULT_MODEL_NAME


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="地质灾害调查系统")
    
    parser.add_argument("--input", "-i", type=str, help="输入图片路径或目录路径")
    parser.add_argument("--model-provider", "-p", type=str, default=DEFAULT_MODEL_PROVIDER,
                       help=f"模型提供商（默认: {DEFAULT_MODEL_PROVIDER}）")
    parser.add_argument("--model-name", "-m", type=str, default=DEFAULT_MODEL_NAME,
                       help=f"模型名称（默认: {DEFAULT_MODEL_NAME}）")
    parser.add_argument("--output", "-o", type=str, default=None,
                       help="输出Excel文件路径（默认使用配置文件中的路径）")
    parser.add_argument("--risk", action="store_true",
                       help="进行风险评价（默认不进行）")
    parser.add_argument("--no-external", action="store_true",
                       help="不补充外部环境数据（默认补充）")
    parser.add_argument("--compare-models", nargs="+", metavar="MODEL",
                       help="使用多个模型进行对比（需要指定图片路径）")
    
    args = parser.parse_args()
    
    # 如果没有指定输入，提示用户
    if not args.input:
        print("错误：请指定输入图片路径或目录")
        parser.print_help()
        sys.exit(1)
    
    # 初始化调度器
    scheduler = SystemScheduler(
        model_provider=args.model_provider,
        model_name=args.model_name,
        output_path=args.output
    )
    
    input_path = Path(args.input)
    
    # 判断是文件还是目录
    if input_path.is_file():
        # 单文件处理
        if args.compare_models:
            # 模型对比模式
            print(f"使用 {len(args.compare_models)} 个模型进行对比...")
            results = scheduler.compare_models(
                str(input_path),
                args.compare_models,
                enable_external_data=not args.no_external
            )
            
            print("\n" + "="*60)
            print("模型对比结果:")
            print("="*60)
            for model_name, result in results.items():
                print(f"\n模型: {model_name}")
                print(f"  风险指数: {result.get('风险指数', 'N/A')}")
                print(f"  风险等级: {result.get('风险等级', 'N/A')}")
                print(f"  规模等级: {result.get('规模等级', 'N/A')}")
        else:
            # 单文件处理
            result = scheduler.process_single_image(
                str(input_path),
                enable_risk_assessment=args.risk,  # 默认False，需要显式指定--risk才进行
                enable_external_data=not args.no_external
            )
            
            if "error" in result:
                print(f"处理失败: {result['error']}")
                sys.exit(1)
            
            print("\n" + "="*60)
            print("处理结果摘要:")
            print("="*60)
            print(f"编号: {result.get('编号', 'N/A')}")
            print(f"位置: {result.get('纬度', 'N/A')}, {result.get('经度', 'N/A')}")
            print(f"规模等级: {result.get('规模等级', 'N/A')}")
            print(f"风险指数: {result.get('风险指数', 'N/A')}")
            print(f"风险等级: {result.get('风险等级', 'N/A')}")
    
    elif input_path.is_dir():
        # 目录批量处理
        print(f"批量处理目录: {input_path}")
        results = scheduler.process_directory(
            str(input_path),
            enable_risk_assessment=args.risk,  # 默认False
            enable_external_data=not args.no_external
        )
        
        print("\n" + "="*60)
        print(f"批量处理完成，共处理 {len(results)} 张图片")
        print("="*60)
        
        # 统计
        success_count = sum(1 for r in results if "error" not in r)
        print(f"成功: {success_count}, 失败: {len(results) - success_count}")
    
    else:
        print(f"错误：输入路径不存在: {args.input}")
        sys.exit(1)


if __name__ == "__main__":
    main()
