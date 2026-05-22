# -*- coding: utf-8 -*-
"""
Few-shot Learning 示例管理模块
功能：加载测试集，构建示例库，为API调用提供参考示例
"""
import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
import base64


class FewShotExampleManager:
    """Few-shot示例管理器"""
    
    def __init__(self, testset_dir: str = None, cache_file: str = None):
        """
        初始化示例管理器
        
        Args:
            testset_dir: 测试集目录路径（包含图片和Excel文件）
            cache_file: 缓存文件路径（用于持久化示例库）
        """
        from config import PROJECT_ROOT
        
        if testset_dir is None:
            testset_dir = os.path.join(PROJECT_ROOT, "测试集")
        self.testset_dir = Path(testset_dir)
        
        if cache_file is None:
            cache_file = os.path.join(PROJECT_ROOT, "output", "few_shot_cache.json")
        self.cache_file = Path(cache_file)
        
        self.examples: List[Dict[str, Any]] = []
        self._load_examples()
    
    def _load_examples(self):
        """加载示例库（优先从缓存加载，否则从测试集构建）"""
        # 检查测试集目录是否存在且有内容
        if not self.testset_dir.exists():
            print(f"测试集目录不存在: {self.testset_dir}，将使用空示例库")
            self.examples = []
            return
        
        # 检查是否有Excel文件
        survey_excel = self.testset_dir / "地质灾害调查结果.xlsx"
        risk_excel = self.testset_dir / "地质灾害风险评价结果.xlsx"
        
        if not survey_excel.exists() and not risk_excel.exists():
            print(f"测试集目录中没有Excel文件，将使用空示例库")
            self.examples = []
            return
        
        # 尝试从缓存加载
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    # 验证缓存是否有效（检查图片文件是否存在）
                    valid_examples = []
                    for ex in cache_data:
                        img_path = Path(ex.get("image_path", ""))
                        if img_path.exists():
                            valid_examples.append(ex)
                    if valid_examples:
                        self.examples = valid_examples
                        print(f"从缓存加载了 {len(self.examples)} 个有效示例")
                        return
                    else:
                        print("缓存中的示例图片已不存在，将从测试集重新构建")
            except Exception as e:
                print(f"加载缓存失败: {e}，将从测试集重新构建")
        
        # 从测试集构建示例库
        self._build_examples_from_testset()
        if self.examples:
            self._save_cache()
    
    def _build_examples_from_testset(self):
        """从测试集构建示例库"""
        print("正在从测试集构建Few-shot示例库...")
        
        # 读取Excel文件
        survey_excel = self.testset_dir / "地质灾害调查结果.xlsx"
        risk_excel = self.testset_dir / "地质灾害风险评价结果.xlsx"
        
        survey_data = {}
        risk_data = {}
        
        if survey_excel.exists():
            try:
                excel_file = pd.ExcelFile(survey_excel)
                print(f"调查结果Excel包含Sheet: {excel_file.sheet_names}")
                for sheet_name in excel_file.sheet_names:
                    df = pd.read_excel(survey_excel, sheet_name=sheet_name)
                    print(f"  Sheet '{sheet_name}': {len(df)} 行")
                    for idx, row in df.iterrows():
                        hazard_id = row.get("灾害点编号") or row.get("编号")
                        if pd.notna(hazard_id):
                            hazard_id = str(hazard_id).strip()
                            if hazard_id in survey_data:
                                print(f"    警告：编号 {hazard_id} 在Sheet '{sheet_name}' 中重复（将覆盖之前的值）")
                            survey_data[hazard_id] = row.to_dict()
                print(f"从调查结果Excel读取了 {len(survey_data)} 条唯一记录，编号列表: {list(survey_data.keys())}")
            except Exception as e:
                print(f"读取调查结果Excel失败: {e}")
        
        if risk_excel.exists():
            try:
                excel_file = pd.ExcelFile(risk_excel)
                print(f"风险评价结果Excel包含Sheet: {excel_file.sheet_names}")
                for sheet_name in excel_file.sheet_names:
                    df = pd.read_excel(risk_excel, sheet_name=sheet_name)
                    print(f"  Sheet '{sheet_name}': {len(df)} 行")
                    for idx, row in df.iterrows():
                        hazard_id = row.get("灾害编号") or row.get("编号")
                        if pd.notna(hazard_id):
                            hazard_id = str(hazard_id).strip()
                            if hazard_id in risk_data:
                                print(f"    警告：编号 {hazard_id} 在Sheet '{sheet_name}' 中重复（将覆盖之前的值）")
                            risk_data[hazard_id] = row.to_dict()
                print(f"从风险评价结果Excel读取了 {len(risk_data)} 条唯一记录，编号列表: {list(risk_data.keys())}")
            except Exception as e:
                print(f"读取风险评价结果Excel失败: {e}")
        
        # 扫描图片文件（只扫描当前目录，不扫描子目录，并去重）
        image_files = []
        seen_paths = set()  # 用于去重
        
        for ext in ["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"]:
            for img_path in self.testset_dir.glob(ext):
                # 只处理当前目录下的文件（不包括子目录）
                if img_path.parent == self.testset_dir:
                    # 使用绝对路径去重（Windows文件系统不区分大小写）
                    abs_path = str(img_path.resolve()).lower()
                    if abs_path not in seen_paths:
                        seen_paths.add(abs_path)
                        image_files.append(img_path)
        
        print(f"扫描到 {len(image_files)} 张图片文件（已去重）")
        if image_files:
            print(f"图片文件列表: {[img.name for img in image_files]}")
        
        examples = []
        matched_count = 0
        
        for img_path in image_files:
            # 从文件名提取编号（去除扩展名）
            hazard_id = img_path.stem.strip()
            
            # 检查是否有对应的Excel数据
            has_survey = hazard_id in survey_data
            has_risk = hazard_id in risk_data
            
            if has_survey or has_risk:
                example = {
                    "hazard_id": hazard_id,
                    "image_path": str(img_path),
                    "survey_data": survey_data.get(hazard_id, {}),
                    "risk_data": risk_data.get(hazard_id, {}),
                }
                examples.append(example)
                matched_count += 1
                print(f"  ✓ 匹配成功: {img_path.name} (编号: {hazard_id}, 有调查数据: {has_survey}, 有风险数据: {has_risk})")
            else:
                print(f"  ✗ 未匹配: {img_path.name} (编号: {hazard_id} 在Excel中找不到对应记录)")
                print(f"    可用的编号列表: 调查数据={list(survey_data.keys())}, 风险数据={list(risk_data.keys())}")
        
        self.examples = examples
        print(f"Few-shot示例库构建完成：共 {len(examples)} 个示例（匹配了 {matched_count}/{len(image_files)} 张图片）")
    
    def _save_cache(self):
        """保存示例库到缓存文件"""
        try:
            # 不保存图片数据，只保存路径和Excel数据
            cache_data = []
            for ex in self.examples:
                cache_data.append({
                    "hazard_id": ex["hazard_id"],
                    "image_path": ex["image_path"],
                    "survey_data": ex["survey_data"],
                    "risk_data": ex["risk_data"],
                })
            
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            print(f"Few-shot示例库已保存到缓存: {self.cache_file}")
        except Exception as e:
            print(f"保存缓存失败: {e}")
    
    def has_examples(self) -> bool:
        """检查是否有可用的示例"""
        return len(self.examples) > 0
    
    def get_examples_for_extraction(self, risk_type: str = None, max_examples: int = 3) -> List[Dict[str, Any]]:
        """
        获取用于指标提取的示例
        
        Args:
            risk_type: 灾害类型（滑坡/崩塌），用于筛选相似示例
            max_examples: 最多返回的示例数量
            
        Returns:
            示例列表
        """
        if not self.examples:
            return []
        
        # 筛选相同类型的示例
        filtered = []
        for ex in self.examples:
            ex_type = ex["survey_data"].get("灾害类型", "")
            if not risk_type or str(ex_type).strip() == str(risk_type).strip():
                filtered.append(ex)
        
        # 返回前N个示例
        return filtered[:max_examples]
    
    def get_examples_for_risk_scoring(self, risk_type: str = None, max_examples: int = 2) -> List[Dict[str, Any]]:
        """
        获取用于风险打分的示例
        
        Args:
            risk_type: 灾害类型（滑坡/崩塌），用于筛选相似示例
            max_examples: 最多返回的示例数量
            
        Returns:
            示例列表
        """
        if not self.examples:
            return []
        
        # 筛选相同类型且有风险评价数据的示例
        filtered = []
        for ex in self.examples:
            if not ex["risk_data"]:
                continue
            ex_type = ex["survey_data"].get("灾害类型", "")
            if not risk_type or str(ex_type).strip() == str(risk_type).strip():
                filtered.append(ex)
        
        return filtered[:max_examples]
    
    def format_example_for_extraction(self, example: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化示例用于指标提取的prompt
        
        Returns:
            {"image": data_url, "text": "示例文本描述", "expected_output": {...}}
        """
        survey = example["survey_data"]
        risk_type = survey.get("灾害类型", "未知")
        
        # 构建示例文本（包含关键指标）
        key_fields = []
        if "坡度" in survey:
            key_fields.append(f"坡度={survey['坡度']}")
        if "物质类型" in survey:
            key_fields.append(f"物质类型={survey['物质类型']}")
        if "破碎程度" in survey:
            key_fields.append(f"破碎程度={survey['破碎程度']}")
        if "风化程度" in survey:
            key_fields.append(f"风化程度={survey['风化程度']}")
        if "植被覆盖" in survey:
            key_fields.append(f"植被覆盖={survey['植被覆盖']}")
        
        example_text = f"示例（灾害类型={risk_type}）"
        if key_fields:
            example_text += "：" + "，".join(key_fields)
        
        # 读取图片并转换为data URL
        img_path = Path(example["image_path"])
        image_url = None
        if img_path.exists():
            try:
                with open(img_path, "rb") as f:
                    img_data = base64.b64encode(f.read()).decode("utf-8")
                ext = img_path.suffix.lower()
                mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
                image_url = f"data:{mime};base64,{img_data}"
            except Exception as e:
                print(f"读取示例图片失败 {img_path}: {e}")
        
        return {
            "image": image_url,
            "text": example_text,
            "expected_output": survey  # 期望的输出结果
        }
    
    def format_example_for_risk_scoring(self, example: Dict[str, Any]) -> Dict[str, Any]:
        """格式化示例用于风险打分的prompt"""
        survey = example["survey_data"]
        risk = example["risk_data"]
        
        # 构建示例文本
        risk_type = survey.get("灾害类型", "未知")
        risk_level = risk.get("风险等级", "未知")
        risk_score = risk.get("风险评价总分", "未知")
        
        example_text = f"示例（灾害类型={risk_type}，风险等级={risk_level}，风险评价总分={risk_score}）"
        
        # 读取图片
        img_path = Path(example["image_path"])
        image_url = None
        if img_path.exists():
            try:
                with open(img_path, "rb") as f:
                    img_data = base64.b64encode(f.read()).decode("utf-8")
                ext = img_path.suffix.lower()
                mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
                image_url = f"data:{mime};base64,{img_data}"
            except Exception as e:
                print(f"读取示例图片失败 {img_path}: {e}")
        
        return {
            "image": image_url,
            "text": example_text,
            "expected_output": risk  # 期望的风险打分结果
        }


if __name__ == "__main__":
    # 测试代码
    manager = FewShotExampleManager()
    print(f"示例数量: {len(manager.examples)}")
    if manager.examples:
        print(f"第一个示例: {manager.examples[0]['hazard_id']}")
