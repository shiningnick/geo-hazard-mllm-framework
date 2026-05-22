# -*- coding: utf-8 -*-
"""
模块3.7：系统调度模块
功能定位：负责控制各模块调用顺序，不参与任何业务判断
"""
from typing import List, Dict, Any, Optional
from modules.image_input import ImageInputManager
from modules.metadata_extraction import MetadataExtractor
from modules.ai_extraction import AIExtractor
from modules.external_data import ExternalDataSupplement
from modules.data_fusion import DataFusion
from modules.risk_assessment import RiskAssessment
from modules.demo_mode import DemoResultProvider, split_demo_record


class SystemScheduler:
    """系统调度器"""
    
    def __init__(self, 
                 model_provider: str = "openai",
                 model_name: str = None,
                 output_path: str = None):
        """
        初始化系统调度器
        
        Args:
            model_provider: 模型提供商
            model_name: 模型名称
            output_path: 输出Excel路径
        """
        # 初始化Few-shot示例管理器（所有模块共享）
        try:
            from modules.few_shot_examples import FewShotExampleManager
            self.example_manager = FewShotExampleManager()
            if self.example_manager.has_examples():
                print(f"Few-shot Learning已启用，加载了 {len(self.example_manager.examples)} 个示例")
            else:
                print("Few-shot Learning未启用（测试集为空）")
                self.example_manager = None
        except Exception as e:
            print(f"初始化Few-shot示例管理器失败: {e}，将不使用Few-shot Learning")
            self.example_manager = None
        
        # 初始化各个模块
        self.image_manager = ImageInputManager()
        self.metadata_extractor = MetadataExtractor()
        self.ai_extractor = AIExtractor(model_provider=model_provider, model_name=model_name,
                                       example_manager=self.example_manager)
        self.external_data = ExternalDataSupplement()
        self.data_fusion = DataFusion(output_path=output_path)
        # 风险评价模块延迟初始化（因为用户可能不需要）
        self.risk_assessor = None
        # 演示模式
        self.demo_provider = DemoResultProvider() if DemoResultProvider.is_enabled() else None
        if self.demo_provider:
            print("演示模式已启用：AI 指标与风险评价将使用 demo_data/sample_results.json")
    
    def process_single_image(self, image_path: str, 
                            enable_risk_assessment: bool = False,
                            enable_external_data: bool = True) -> Dict[str, Any]:
        """
        处理单张图片的完整流程
        
        Args:
            image_path: 图片路径
            enable_risk_assessment: 是否进行风险评价
            enable_external_data: 是否补充外部数据
            
        Returns:
            处理结果字典
        """
        print(f"\n开始处理图片: {image_path}")
        
        # 步骤1：图片输入与管理
        print("步骤1：图片输入与管理...")
        image_info = self.image_manager.add_image(image_path)
        if not image_info.get("exists"):
            return {"error": f"图片不存在: {image_path}", "image_info": image_info}
        
        # 步骤2：提取基础信息（客观信息）
        print("步骤2：提取基础信息...")
        basic_info = self.metadata_extractor.extract_standard_fields(image_path)
        
        demo_record = None
        if self.demo_provider:
            demo_record = self.demo_provider.lookup(image_path)

        # 步骤3：AI图像语义理解与地质判识
        print("步骤3：AI图像语义理解与地质判识...")
        if demo_record:
            ai_extraction, preset_risk = split_demo_record(demo_record)
            print("  （演示模式：使用预置指标）")
        else:
            ai_extraction = self.ai_extractor.extract_indicators(image_path)
            preset_risk = {}
        
        # 步骤4：外部环境数据补充（可选）
        external_data = {}
        if enable_external_data and basic_info.get("纬度") and basic_info.get("经度") and basic_info.get("拍摄日期"):
            print("步骤4：补充外部环境数据...")
            if self.demo_provider:
                print("  （演示模式：跳过外部 API，使用空值占位）")
            else:
                external_data = self.external_data.supplement_all(
                    basic_info["纬度"],
                    basic_info["经度"],
                    basic_info["拍摄日期"]
                )
        else:
            print("步骤4：跳过外部环境数据补充（缺少必要信息）")
        
        # 步骤5：指标融合
        print("步骤5：指标融合...")
        fused_record = self.data_fusion.fuse_data(basic_info, ai_extraction, external_data)
        
        # 步骤6：风险评价（可选，默认关闭）
        if enable_risk_assessment:
            print("步骤6：风险评价...")
            if preset_risk:
                fused_record.update(preset_risk)
                print("  （演示模式：使用预置风险评价）")
            else:
                try:
                    if self.risk_assessor is None:
                        self.risk_assessor = RiskAssessment(
                            model_provider=self.ai_extractor.model_provider,
                            model_name=self.ai_extractor.model_name,
                            example_manager=self.example_manager
                        )
                    risk_result = self.risk_assessor.assess_risk(fused_record, image_path)
                    fused_record.update(risk_result)
                except Exception as e:
                    print(f"风险评价失败: {e}，继续保存其他数据")
                    import traceback
                    traceback.print_exc()
        else:
            print("步骤6：跳过风险评价（默认关闭）")
        
        # 步骤7：保存到Excel
        print("步骤7：保存到Excel...")
        self.data_fusion.save_to_excel(fused_record, append=True)
        
        print(f"处理完成: {image_path}")
        return fused_record
    
    def process_batch_images(self, 
                            image_paths: List[str],
                            enable_risk_assessment: bool = False,
                            enable_external_data: bool = True) -> List[Dict[str, Any]]:
        """
        批量处理图片
        
        Args:
            image_paths: 图片路径列表
            enable_risk_assessment: 是否进行风险评价
            enable_external_data: 是否补充外部数据
            
        Returns:
            处理结果列表
        """
        results = []
        
        for i, image_path in enumerate(image_paths, 1):
            print(f"\n{'='*60}")
            print(f"处理进度: {i}/{len(image_paths)}")
            print(f"{'='*60}")
            
            try:
                result = self.process_single_image(
                    image_path,
                    enable_risk_assessment=enable_risk_assessment,
                    enable_external_data=enable_external_data
                )
                results.append(result)
            except Exception as e:
                print(f"处理图片 {image_path} 时出错: {e}")
                results.append({"error": str(e), "image_path": image_path})
        
        # 统计分类信息
        success_results = [r for r in results if "error" not in r]
        if success_results:
            type_count = {}
            for result in success_results:
                risk_type = result.get("风险类型", "未知")
                type_count[risk_type] = type_count.get(risk_type, 0) + 1
            
            print(f"\n处理完成统计:")
            print(f"  成功: {len(success_results)} 张")
            print(f"  失败: {len(results) - len(success_results)} 张")
            if type_count:
                print(f"  分类统计:")
                for risk_type, count in sorted(type_count.items()):
                    sheet_name = self.data_fusion._get_sheet_name({"风险类型": risk_type})
                    print(f"    {risk_type} ({sheet_name} sheet): {count} 张")
        
        return results
    
    def process_directory(self, 
                         directory: str = None,
                         enable_risk_assessment: bool = False,
                         enable_external_data: bool = True) -> List[Dict[str, Any]]:
        """
        处理目录中的所有图片
        
        Args:
            directory: 目录路径，如果为None则使用默认输入目录
            enable_risk_assessment: 是否进行风险评价
            enable_external_data: 是否补充外部数据
            
        Returns:
            处理结果列表
        """
        # 扫描目录中的图片
        image_list = self.image_manager.scan_directory(directory)
        image_paths = [img["path"] for img in image_list if img.get("exists")]
        
        if not image_paths:
            print(f"在目录 {directory or '默认目录'} 中未找到图片文件")
            return []
        
        print(f"找到 {len(image_paths)} 张图片")
        return self.process_batch_images(image_paths, enable_risk_assessment, enable_external_data)
    
    def compare_models(self, 
                      image_path: str,
                      model_names: List[str],
                      enable_external_data: bool = True) -> Dict[str, Dict[str, Any]]:
        """
        使用多个模型处理同一张图片，用于对比
        
        Args:
            image_path: 图片路径
            model_names: 模型名称列表
            enable_external_data: 是否补充外部数据
            
        Returns:
            {模型名称: 处理结果} 字典
        """
        print(f"\n开始模型对比: {image_path}")
        
        # 提取基础信息（所有模型共用）
        basic_info = self.metadata_extractor.extract_standard_fields(image_path)
        
        # 外部数据（所有模型共用）
        external_data = {}
        if enable_external_data and basic_info.get("纬度") and basic_info.get("经度") and basic_info.get("拍摄日期"):
            external_data = self.external_data.supplement_all(
                basic_info["纬度"],
                basic_info["经度"],
                basic_info["拍摄日期"]
            )
        
        # 使用不同模型提取
        ai_results = self.ai_extractor.extract_with_multiple_models(image_path, model_names)
        
        # 融合结果
        results = {}
        for model_name, ai_extraction in ai_results.items():
            fused_record = self.data_fusion.fuse_data(basic_info, ai_extraction, external_data)
            # 风险评价（可选）
            if self.risk_assessor is not None:
                try:
                    risk_result = self.risk_assessor.assess_risk(fused_record, image_path)
                    fused_record.update(risk_result)
                except Exception as e:
                    print(f"风险评价失败: {e}，继续保存其他数据")
            results[model_name] = fused_record
        
        return results


if __name__ == "__main__":
    # 测试代码
    scheduler = SystemScheduler(
        model_provider="openai",
        model_name="gpt-5-nano-2025-08-07"
    )
    
    test_image = r"C:\Users\UCD-K\Desktop\科研工作\文章撰写-AI赋能地质调查\地质调查一张图\图片测试\A1.jpg"
    result = scheduler.process_single_image(test_image)
    print("\n处理结果:")
    print(result)
