# -*- coding: utf-8 -*-
"""
模块3.5：指标融合与结构化输出模块
功能定位：将多来源指标整合为一条标准化地质灾害点结构记录，保存至Excel表格
支持按灾害类型自动分类保存到不同的sheet
"""
import pandas as pd
from typing import Dict, Any, List, Optional
from pathlib import Path
from config import EXCEL_OUTPUT_PATH, EXCEL_SHEET_NAME


class DataFusion:
    """指标融合与结构化输出类"""
    
    def __init__(self, output_path: str = None, sheet_name: str = None):
        """
        初始化数据融合器
        
        Args:
            output_path: Excel输出路径，如果为None则使用默认路径
            sheet_name: Excel工作表名称（已废弃，现在按风险类型自动分类）
        """
        if output_path is None:
            output_path = EXCEL_OUTPUT_PATH
        
        self.output_path = output_path
        
        # 灾害类型到sheet名称的映射（FHWA框架：只分滑坡和崩塌）
        self.hazard_type_to_sheet = {
            "滑坡": "滑坡",
            "崩塌": "崩塌",
        }
        
        # 默认sheet名称（用于未分类的数据）
        self.default_sheet_name = "未分类"
        
        # 确保输出目录存在
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    def _get_output_field_mapping(self, risk_type: str) -> Dict[str, str]:
        """
        获取输出字段名称映射（代码内部名称 -> 规范输出名称）
        
        Args:
            risk_type: 风险类型（滑坡或崩塌）
            
        Returns:
            字段映射字典 {内部名称: 规范名称}
        """
        base_mapping = {
            "编号": "灾害点编号",
            "风险类型": "灾害类型",
            "经度": "经度",
            "纬度": "纬度",
            "高程_m": "高程",
            "拍摄日期": "调查时间",
            "坡度等级": "坡度",
            "地貌单元": "地貌单元",
            "物质类型": "物质类型",
            "破碎程度": "破碎程度",
            "风化程度": "风化程度",
            "植被覆盖": "植被覆盖",
            "裂缝发育": "裂缝发育",
            "新鲜破坏": "新鲜破坏迹象",
            "工程扰动": "工程扰动程度",
            "防护类型": "防护类型",
            "诱发因素": "诱发因素",
            "威胁对象": "威胁对象",
            "降水_当日_mm": "当日降水量",
            "降水_前30日_mm": "前30日累计降水",
            "降水_前180日_mm": "前180日累计降水",
            "降水_前365日_mm": "前365日累计降水",
            "地震烈度": "工程设计地震烈度",
            "地震_epa": "地震动峰值加速度",
        }
        
        if risk_type == "滑坡":
            base_mapping.update({
                "滑坡破坏方式": "滑坡子类型（运动方式）",
                "滑坡当前活动状态": "当前活动状态",
                "滑坡变形阶段": "变形发展阶段",
                "滑坡水作用强度": "水对滑坡的控制作用",
                "滑坡致灾方式": "对工程的主要作用方式",
            })
        elif risk_type == "崩塌":
            base_mapping.update({
                "崩塌类型": "崩塌子类型",
                "崩塌近期活动性": "近期落石活动迹象",
                "崩塌传播可达性": "落石传播可达性",
                "崩塌防护有效性": "防护工程有效性",
                "崩塌致灾方式": "对工程的致灾形式",
            })
        
        return base_mapping
    
    def _get_output_field_order(self, risk_type: str) -> List[str]:
        """
        获取输出字段顺序（按规范要求）
        
        Args:
            risk_type: 风险类型（滑坡或崩塌）
            
        Returns:
            字段名称列表（按规范顺序）
        """
        if risk_type == "滑坡":
            return [
                "灾害点编号",
                "灾害类型",
                "滑坡子类型（运动方式）",
                "滑坡子类型（物质与状态）",
                "经度",
                "纬度",
                "高程",
                "调查时间",
                "当日降水量",
                "前30日累计降水",
                "前180日累计降水",
                "前365日累计降水",
                "工程设计地震烈度",
                "地震动峰值加速度",
                "坡度",
                "地貌单元",
                "物质类型",
                "破碎程度",
                "风化程度",
                "植被覆盖",
                "裂缝发育",
                "新鲜破坏迹象",
                "工程扰动程度",
                "防护类型",
                "诱发因素",
                "威胁对象",
                "当前活动状态",
                "变形发展阶段",
                "水对滑坡的控制作用",
                "对工程的主要作用方式",
            ]
        elif risk_type == "崩塌":
            return [
                "灾害点编号",
                "灾害类型",
                "崩塌子类型",
                "经度",
                "纬度",
                "高程",
                "调查时间",
                "当日降水量",
                "前30日累计降水",
                "前180日累计降水",
                "前365日累计降水",
                "工程设计地震烈度",
                "地震动峰值加速度",
                "坡度",
                "地貌单元",
                "物质类型",
                "破碎程度",
                "风化程度",
                "植被覆盖",
                "裂缝发育",
                "新鲜破坏迹象",
                "工程扰动程度",
                "防护类型",
                "诱发因素",
                "威胁对象",
                "近期落石活动迹象",
                "落石传播可达性",
                "防护工程有效性",
                "对工程的致灾形式",
            ]
        else:
            return []
    
    def _map_and_order_fields(self, record: Dict[str, Any], risk_type: str) -> Dict[str, Any]:
        """
        映射字段名称并按规范顺序排列
        
        Args:
            record: 原始记录（使用内部字段名）
            risk_type: 风险类型
            
        Returns:
            映射后的记录（使用规范字段名，按规范顺序）
        """
        mapping = self._get_output_field_mapping(risk_type)
        order = self._get_output_field_order(risk_type)
        
        # 反向映射：规范名称 -> 代码内部名称
        reverse_mapping = {v: k for k, v in mapping.items()}
        
        # 创建映射后的记录（按规范顺序）
        mapped_record = {}
        # #region agent log
        import json as json_module
        import os
        log_path = r"d:\地质灾害一张图\.cursor\debug.log"
        def debug_log(location, message, data, hypothesis_id):
            try:
                with open(log_path, 'a', encoding='utf-8') as f:
                    f.write(json_module.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":hypothesis_id,"location":location,"message":message,"data":data,"timestamp":int(__import__('time').time()*1000)})+"\n")
            except: pass
        # #endregion
        
        for output_name in order:
            internal_name = reverse_mapping.get(output_name)
            if internal_name and internal_name in record:
                value = record[internal_name]
                # 只添加非None的值（None值不输出）
                if value is not None:
                    # 检查是否为多选字段
                    is_multi_field = output_name in ["诱发因素", "威胁对象", "防护类型"]
                    debug_log("data_fusion.py:201", "mapping field", {"output_name":output_name,"internal_name":internal_name,"value":value,"value_type":type(value).__name__,"is_multi_field":is_multi_field}, "B")
                    mapped_record[output_name] = value
            elif output_name in record:
                # 如果已经是规范名称，直接使用
                value = record[output_name]
                if value is not None:
                    is_multi_field = output_name in ["诱发因素", "威胁对象", "防护类型"]
                    debug_log("data_fusion.py:208", "using direct field", {"output_name":output_name,"value":value,"value_type":type(value).__name__,"is_multi_field":is_multi_field}, "B")
                    mapped_record[output_name] = value
        
        debug_log("data_fusion.py:212", "mapped_record final", {"诱发因素":mapped_record.get("诱发因素"),"威胁对象":mapped_record.get("威胁对象"),"防护类型":mapped_record.get("防护类型")}, "B")
        return mapped_record
    
    def fuse_data(self, 
                  basic_info: Dict[str, Any],
                  ai_extraction: Dict[str, Any],
                  external_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        融合多来源数据为一条标准化记录
        
        Args:
            basic_info: 基础信息（来自metadata_extraction模块）
            ai_extraction: AI提取的指标（来自ai_extraction模块）
            external_data: 外部环境数据（来自external_data模块）
            
        Returns:
            融合后的标准化记录字典
        """
        # 创建融合后的记录
        fused_record = {}
        
        # 1. 基本信息（编号、经纬度、高程、拍摄日期等）
        fused_record.update(basic_info)
        
        # 2. AI提取的指标
        fused_record.update(ai_extraction)
        
        # 3. 外部环境数据
        fused_record.update(external_data)
        
        return fused_record
    
    def _get_sheet_name(self, record: Dict[str, Any]) -> str:
        """
        根据记录的风险类型获取对应的sheet名称
        
        Args:
            record: 记录字典
            
        Returns:
            sheet名称
        """
        risk_type = record.get("风险类型", "").strip()
        if risk_type in self.hazard_type_to_sheet:
            return self.hazard_type_to_sheet[risk_type]
        else:
            # 如果风险类型未知或不存在，保存到"其他"
            return self.default_sheet_name
    
    def save_to_excel(self, record: Dict[str, Any], append: bool = True) -> None:
        """
        保存记录到Excel文件，根据风险类型自动分类到不同的sheet
        
        Args:
            record: 要保存的记录字典（使用内部字段名）
            append: 是否追加到现有文件（True）还是覆盖（False）
        """
        # 获取对应的sheet名称
        sheet_name = self._get_sheet_name(record)
        risk_type = record.get("风险类型", "未知")
        
        # 映射字段名称并按规范顺序排列
        mapped_record = self._map_and_order_fields(record, risk_type)
        
        # 将记录转换为DataFrame
        df_new = pd.DataFrame([mapped_record])
        
        # 读取现有Excel文件的所有sheet（如果存在）
        existing_sheets = {}
        if append and Path(self.output_path).exists():
            try:
                excel_file = pd.ExcelFile(self.output_path)
                for sheet in excel_file.sheet_names:
                    existing_sheets[sheet] = pd.read_excel(self.output_path, sheet_name=sheet)
            except Exception as e:
                print(f"读取现有Excel文件失败，将创建新文件: {e}")
        
        # 合并数据到对应的sheet
        if sheet_name in existing_sheets:
            df_combined = pd.concat([existing_sheets[sheet_name], df_new], ignore_index=True)
        else:
            df_combined = df_new
        
        existing_sheets[sheet_name] = df_combined
        
        # 保存所有sheet到Excel
        with pd.ExcelWriter(self.output_path, engine='openpyxl', mode='w') as writer:
            for sheet, df in existing_sheets.items():
                df.to_excel(writer, sheet_name=sheet, index=False)
        
        print(f"数据已保存到: {self.output_path} (Sheet: {sheet_name}, 风险类型: {risk_type})")
    
    def save_batch_to_excel(self, records: List[Dict[str, Any]], append: bool = True) -> None:
        """
        批量保存记录到Excel文件，根据风险类型自动分类到不同的sheet
        
        Args:
            records: 要保存的记录字典列表（使用内部字段名）
            append: 是否追加到现有文件（True）还是覆盖（False）
        """
        if not records:
            print("没有记录需要保存")
            return
        
        # 读取现有Excel文件的所有sheet（如果存在）
        existing_sheets = {}
        if append and Path(self.output_path).exists():
            try:
                excel_file = pd.ExcelFile(self.output_path)
                for sheet in excel_file.sheet_names:
                    existing_sheets[sheet] = pd.read_excel(self.output_path, sheet_name=sheet)
            except Exception as e:
                print(f"读取现有Excel文件失败，将创建新文件: {e}")
        
        # 按风险类型分组并映射字段
        records_by_sheet = {}
        for record in records:
            sheet_name = self._get_sheet_name(record)
            risk_type = record.get("风险类型", "未知")
            
            # 映射字段名称并按规范顺序排列
            mapped_record = self._map_and_order_fields(record, risk_type)
            
            if sheet_name not in records_by_sheet:
                records_by_sheet[sheet_name] = []
            records_by_sheet[sheet_name].append(mapped_record)
        
        # 合并每个sheet的数据
        for sheet_name, sheet_records in records_by_sheet.items():
            df_new = pd.DataFrame(sheet_records)
            
            if sheet_name in existing_sheets:
                df_combined = pd.concat([existing_sheets[sheet_name], df_new], ignore_index=True)
            else:
                df_combined = df_new
            
            existing_sheets[sheet_name] = df_combined
        
        # 保存所有sheet到Excel
        with pd.ExcelWriter(self.output_path, engine='openpyxl', mode='w') as writer:
            for sheet, df in existing_sheets.items():
                df.to_excel(writer, sheet_name=sheet, index=False)
        
        # 统计信息
        summary = ", ".join([f"{sheet}: {len(existing_sheets[sheet])}条" 
                            for sheet in sorted(existing_sheets.keys())])
        print(f"已保存 {len(records)} 条记录到: {self.output_path}")
        print(f"分类统计: {summary}")
    
    def read_from_excel(self, sheet_name: str = None) -> pd.DataFrame:
        """
        从Excel文件读取数据
        
        Args:
            sheet_name: 要读取的sheet名称，如果为None则读取第一个sheet
        
        Returns:
            DataFrame对象
        """
        if not Path(self.output_path).exists():
            return pd.DataFrame()
        
        try:
            if sheet_name is None:
                # 读取第一个sheet
                return pd.read_excel(self.output_path, sheet_name=0)
            else:
                return pd.read_excel(self.output_path, sheet_name=sheet_name)
        except Exception as e:
            print(f"读取Excel文件失败: {e}")
            return pd.DataFrame()
    
    def read_all_sheets(self) -> Dict[str, pd.DataFrame]:
        """
        读取Excel文件的所有sheet
        
        Returns:
            {sheet名称: DataFrame} 字典
        """
        if not Path(self.output_path).exists():
            return {}
        
        try:
            excel_file = pd.ExcelFile(self.output_path)
            result = {}
            for sheet in excel_file.sheet_names:
                result[sheet] = pd.read_excel(self.output_path, sheet_name=sheet)
            return result
        except Exception as e:
            print(f"读取Excel文件失败: {e}")
            return {}


if __name__ == "__main__":
    # 测试代码
    fusion = DataFusion()
    
    # 示例数据
    basic_info = {
        "编号": "A1",
        "纬度": 29.5,
        "经度": 103.5,
        "高程_m": 1200.5,
        "拍摄日期": "2023-03-31"
    }
    
    ai_extraction = {
        "滑坡类型": "土质滑坡",
        "规模等级": "中型",
        "平面形态": "舌形"
    }
    
    external_data = {
        "降水_前15日_mm": 50.0,
        "地震烈度": 6.0
    }
    
    record = fusion.fuse_data(basic_info, ai_extraction, external_data)
    fusion.save_to_excel(record, append=False)
