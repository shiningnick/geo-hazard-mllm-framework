# -*- coding: utf-8 -*-
"""
模块3.6：风险评价模块
功能定位：在前文调查与AI提取结果的基础上，参考 FHWA 的道路滑坡 / 崩塌危险性评价方法，
          对同质化路段的地质灾害点进行图像定性打分与综合风险分级。

设计要求：
1. 将“风险打分依据（各指标赋值规则）”和“风险评价过程（汇总与分级）”拆分为两个层次函数；
2. 风险指标打分基于大模型，结合图像和前面提取的指标来进行FHWA打分；
3. 支持滑坡（Landslide）与崩塌 / 落石（Rockfall）两类危险性评价；
4. 评价结果单独输出为一个 Excel：列为灾害编号、灾害类型、各指标风险得分、风险评价总分、风险等级。
"""
from typing import Dict, Any, List, Optional
from pathlib import Path
import base64
import json
import time
import httpx

import pandas as pd
from openai import OpenAI

from config import RISK_EXCEL_OUTPUT_PATH, OUTPUT_DIR, MODEL_CONFIGS, DEFAULT_MODEL_PROVIDER, DEFAULT_MODEL_NAME


class RiskAssessment:
    """
    FHWA 风险评价类

    核心分两层：
    1）compute_indicator_scores：调用大模型API，结合图像和已提取指标，给出 A/B/C/... 等指标的 3/9/27/81 赋值；
    2）aggregate_risk：在指标得分基础上计算总分、归一化风险指数（0-100）并给出风险等级。
    """

    def __init__(self, output_path: str = None, model_provider: str = None, model_name: str = None,
                 example_manager=None):
        """
        初始化风险评价器
        
        Args:
            output_path: 风险结果 Excel 路径
            model_provider: 模型提供商，默认使用配置中的默认值
            model_name: 模型名称，默认使用配置中的默认值
            example_manager: Few-shot示例管理器，如果为None则自动初始化
        """
        # 风险结果 Excel 路径
        if output_path is None:
            output_path = RISK_EXCEL_OUTPUT_PATH
        self.output_path = Path(output_path)
        
        # 初始化大模型客户端
        self.model_provider = model_provider or DEFAULT_MODEL_PROVIDER
        self.model_config = MODEL_CONFIGS.get(self.model_provider, {})
        self.model_name = model_name or DEFAULT_MODEL_NAME
        self.client = self._init_client()
        
        # 初始化Few-shot示例管理器
        if example_manager is None:
            try:
                from modules.few_shot_examples import FewShotExampleManager
                self.example_manager = FewShotExampleManager()
                if self.example_manager.has_examples():
                    print(f"风险评价Few-shot Learning已启用，加载了 {len(self.example_manager.examples)} 个示例")
            except Exception as e:
                print(f"初始化Few-shot示例管理器失败: {e}，将不使用Few-shot Learning")
                self.example_manager = None
        else:
            self.example_manager = example_manager

    def _init_client(self) -> OpenAI:
        """初始化API客户端"""
        timeout = self.model_config.get("timeout", 300)  # 默认300秒
        return OpenAI(
            api_key=self.model_config.get("api_key"),
            base_url=self.model_config.get("base_url"),
            timeout=httpx.Timeout(timeout, connect=30)  # 连接超时30秒，总超时300秒
        )

    def _image_to_data_url(self, image_path: str) -> str:
        """将图片转换为data URL格式"""
        ext = image_path.lower()
        if ext.endswith(".png"):
            mime = "image/png"
        elif ext.endswith((".jpg", ".jpeg")):
            mime = "image/jpeg"
        else:
            mime = "application/octet-stream"
        
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime};base64,{b64}"

    # ------------------------------------------------------------------
    # 对外主接口
    # ------------------------------------------------------------------
    def assess_risk(self, record: Dict[str, Any], image_path: Optional[str] = None) -> Dict[str, Any]:
        """
        对单条“融合后记录”进行 FHWA 风险评价。

        入参 record 通常为 system_scheduler 经过 data_fusion 后的 fused_record，
        已包含：风险类型、通用指标（裂缝发育 / 新鲜破坏 / 工程扰动 等）、
        以及外部数据（前365日累计降雨量等）。
        
        Args:
            record: 融合后的记录
            image_path: 图像路径，如果提供则调用大模型进行打分
        """
        risk_type = str(record.get("风险类型", "未知")).strip()

        # 1. 按灾害类型计算各指标得分（打分依据函数）- 调用大模型API
        indicator_scores = self.compute_indicator_scores(record, risk_type, image_path)

        # 2. 根据指标得分汇总风险总分/指数/等级（评价过程函数）
        risk_summary = self.aggregate_risk(indicator_scores, risk_type)

        # 3. 组织返回结果（供主流程合并到 fused_record，也用于写 Excel）
        result: Dict[str, Any] = {}
        result.update(indicator_scores)
        result.update(risk_summary)

        # 附加基础字段，便于单独 Excel 输出
        result["灾害编号"] = record.get("编号") or record.get("灾害点编号") or record.get("影像编号") or "未知"
        result["灾害类型"] = risk_type or "未知"

        # 4. 写入风险评价专用 Excel（逐条追加）
        try:
            self._save_result_to_excel(result)
        except Exception:
            # 不让 Excel 写入错误影响主流程
            pass

        return result

    def assess_batch(self, records: List[Dict[str, Any]], image_paths: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        批量风险评价（供脚本或后续扩展使用）。
        
        Args:
            records: 记录列表
            image_paths: 图像路径列表，如果提供则与records一一对应
        """
        results: List[Dict[str, Any]] = []
        for i, record in enumerate(records):
            image_path = image_paths[i] if image_paths and i < len(image_paths) else None
            assessment = self.assess_risk(record, image_path)
            record.update(assessment)
            results.append(record)
        return results

    # ------------------------------------------------------------------
    # 一、风险“打分依据”层：调用大模型API，结合图像和已提取指标为 A/B/C/... 赋 3/9/27/81
    # ------------------------------------------------------------------
    def compute_indicator_scores(self, record: Dict[str, Any], risk_type: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """
        调用大模型API，结合图像和已提取指标，计算各 FHWA 风险指标的赋分结果。

        返回示例（滑坡）：{
            "A 道路受影响程度": 27,
            "B 滑动/侵蚀效应": 9,
            "C 受影响道路长度": 27,
            "I 边坡排水": 81,
            "J 年降雨量（湿润度）": 27,
            "K 坡高/滑坡轴向尺度": 9,
            "L 冻融稳定性": 3,
        }
        
        Args:
            record: 已提取的指标记录
            risk_type: 风险类型（滑坡或崩塌）
            image_path: 图像路径，如果提供则调用大模型
        """
        risk_type = (risk_type or "").strip()
        
        # 如果没有图像路径，使用本地规则打分（向后兼容）
        if not image_path:
            return self._compute_scores_local(record, risk_type)
        
        # 调用大模型API进行打分
        try:
            return self._compute_scores_with_ai(record, risk_type, image_path)
        except Exception as e:
            print(f"大模型风险打分失败: {e}，回退到本地规则打分")
            import traceback
            traceback.print_exc()
            return self._compute_scores_local(record, risk_type)

    def _compute_scores_with_ai(self, record: Dict[str, Any], risk_type: str, image_path: str) -> Dict[str, Any]:
        """
        调用大模型API，结合图像和已提取指标进行FHWA风险打分
        """
        # 构建已提取指标的参考信息
        extracted_indicators = self._format_extracted_indicators(record, risk_type)
        
        # 生成Prompt
        system_prompt, user_prompt = self._generate_risk_scoring_prompt(risk_type, extracted_indicators)
        
        # 调用API
        data_url = self._image_to_data_url(image_path)
        
        # 添加重试机制和总时长控制
        max_retries = 3
        retry_delay = 5
        step_timeout = self.model_config.get("timeout", 300)
        step_start_time = time.time()
        
        result = None
        last_error = None
        
        for attempt in range(max_retries):
            # 检查本阶段累计耗时，确保不超过 step_timeout
            elapsed_step = time.time() - step_start_time
            if elapsed_step > step_timeout:
                print(f"风险打分阶段总耗时已超过 {step_timeout} 秒，停止重试")
                if last_error:
                    raise last_error
                raise TimeoutError(f"风险打分阶段超时（>{step_timeout}秒）")
            
            try:
                print(f"正在调用API进行风险打分（尝试 {attempt + 1}/{max_retries}）...")
                print(f"[API请求] System Prompt: {system_prompt[:200]}..." if len(system_prompt) > 200 else f"[API请求] System Prompt: {system_prompt}")
                print(f"[API请求] User Prompt长度: {len(user_prompt)} 字符")
                print(f"[API请求] 模型: {self.model_name}")
                start_time = time.time()
                
                # 构建消息内容（包含Few-shot示例图片）
                user_content = [{"type": "text", "text": user_prompt}]
                
                # 添加Few-shot示例图片
                if self.example_manager and self.example_manager.has_examples():
                    examples = self.example_manager.get_examples_for_risk_scoring(risk_type=risk_type, max_examples=2)
                    for ex in examples:
                        formatted = self.example_manager.format_example_for_risk_scoring(ex)
                        if formatted.get("image"):
                            user_content.append({
                                "type": "image_url",
                                "image_url": {"url": formatted["image"]}
                            })
                
                # 添加待打分的图片
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": data_url}
                })
                
                # 使用标准的OpenAI chat completions API格式
                resp = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {
                            "role": "system",
                            "content": system_prompt
                        },
                        {
                            "role": "user",
                            "content": user_content
                        }
                    ],
                )
                
                elapsed_time = time.time() - start_time
                print(f"风险打分API调用完成，耗时: {elapsed_time:.2f} 秒")
                
                # 检查响应对象（标准OpenAI格式，优先检查choices）
                if hasattr(resp, 'choices') and resp.choices:
                    raw_text = resp.choices[0].message.content
                elif hasattr(resp, 'output_text'):
                    raw_text = (resp.output_text or "").strip()
                elif hasattr(resp, 'text'):
                    raw_text = resp.text
                elif hasattr(resp, 'content'):
                    raw_text = resp.content
                else:
                    raise ValueError(f"无法从响应中提取文本，响应对象: {resp}")
                
                if not raw_text:
                    raise ValueError("响应文本为空")
                
                # 输出API响应内容（用于调试）
                print(f"[API响应] 原始响应长度: {len(raw_text)} 字符")
                print(f"[API响应] 原始响应内容: {raw_text[:500]}..." if len(raw_text) > 500 else f"[API响应] 原始响应内容: {raw_text}")
                
                # 解析JSON结果
                result = self._parse_risk_scores_json(raw_text, risk_type)
                print(f"[API解析] 解析后的风险打分: {result}")
                break  # 成功，跳出重试循环
                
            except Exception as e:
                last_error = e
                elapsed_time = time.time() - start_time if 'start_time' in locals() else 0
                print(f"风险打分API调用失败（尝试 {attempt + 1}/{max_retries}，耗时 {elapsed_time:.2f} 秒）: {e}")
                
                if attempt < max_retries - 1:
                    # 再次检查剩余可用时间，避免总时长超过 step_timeout
                    now = time.time()
                    elapsed_step = now - step_start_time
                    remaining = step_timeout - elapsed_step
                    if remaining <= 0:
                        print(f"风险打分阶段剩余时间不足（{remaining:.2f} 秒），不再重试")
                        raise last_error
                    
                    sleep_time = min(retry_delay, max(0, remaining))
                    print(f"等待 {sleep_time:.2f} 秒后重试...（本阶段剩余可用时间约 {remaining:.2f} 秒）")
                    time.sleep(sleep_time)
                else:
                    print(f"所有重试均失败，最后错误: {last_error}")
                    raise last_error
        
        if result is None:
            raise ValueError(f"API调用失败，无法获取结果。最后错误: {last_error}")
        
        return result

    def _format_extracted_indicators(self, record: Dict[str, Any], risk_type: str) -> str:
        """
        格式化已提取的指标，作为大模型的参考信息
        """
        lines = ["## 已提取的指标信息（仅供参考，请结合图像进行最终判断）"]
        
        # 通用指标
        common_fields = [
            "坡度等级", "地貌单元", "物质类型", "破碎程度", "风化程度", 
            "植被覆盖", "裂缝发育", "新鲜破坏", "工程扰动", "防护类型",
            "诱发因素", "威胁对象"
        ]
        
        for field in common_fields:
            value = record.get(field)
            if value and value != "未知":
                lines.append(f"- {field}: {value}")
        
        # 滑坡特定指标
        if risk_type == "滑坡":
            landslide_fields = [
                "滑坡破坏方式", "滑坡当前活动状态", 
                "滑坡变形阶段", "滑坡水作用强度", "滑坡致灾方式"
            ]
            for field in landslide_fields:
                value = record.get(field)
                if value and value != "未知":
                    lines.append(f"- {field}: {value}")
        
        # 崩塌特定指标
        elif risk_type == "崩塌":
            rockfall_fields = [
                "崩塌类型", "崩塌近期活动性", "崩塌传播可达性",
                "崩塌防护有效性", "崩塌致灾方式"
            ]
            for field in rockfall_fields:
                value = record.get(field)
                if value and value != "未知":
                    lines.append(f"- {field}: {value}")
        
        # 外部数据
        external_fields = [
            "降水_当日_mm", "降水_前30日_mm", "降水_前180日_mm", "降水_前365日_mm",
            "地震烈度", "地震_epa"
        ]
        for field in external_fields:
            value = record.get(field)
            if value is not None:
                lines.append(f"- {field}: {value}")
        
        return "\n".join(lines)

    def _generate_risk_scoring_prompt(self, risk_type: str, extracted_indicators: str) -> tuple[str, str]:
        """
        生成风险打分的Prompt
        
        Returns:
            (system_prompt, user_prompt)
        """
        system_prompt = """你是FHWA道路地质灾害风险评估专家。
你必须只输出严格 JSON，不要任何解释、不要 Markdown、不要多余文字。
根据图像和已提取的指标信息，按照FHWA标准对各项风险指标进行打分（3/9/27/81）。"""
        
        if risk_type == "滑坡":
            user_prompt = f"""请根据图像和已提取的指标信息，按照FHWA标准对滑坡（Landslide）的各项风险指标进行打分。

{extracted_indicators}

## FHWA滑坡风险评价指标及打分标准

### A. 道路受影响程度（3/9/27/81）
- 3分：车辆基本可按常规路线通过；仅见轻微裂缝/薄层泥砂/局部路肩轻损
- 9分：需轻度绕行/贴线通过；堆积或沉陷主要占据路缘/路肩或车道边缘
- 27分：需明显避让或交替通行；堆积/沉陷/错台对车道形成"实体障碍感"
- 81分：基本阻断通行/明显封闭条件；路面出现断坎、塌陷贯穿、堆积形成"墙式阻挡"

### B. 滑动/侵蚀效应（3/9/27/81）
- 3分：仅轻微波浪、细裂缝、薄层堆积；不影响车辆姿态与稳定性
- 9分：可感知的变形：路面出现可见台阶/下沉/隆起，车辆通过需要减速但仍可控
- 27分：显著变形：连续错台、明显沉陷带、轮迹被迫改变
- 81分：严重破坏：断面破坏、深坑/大断坎、路基边缘明显悬空或被冲毁

### C. 受影响道路长度（3/9/27/81）
- 3分：影响呈点状/短小段：损坏集中在单一位置
- 9分：影响呈短段连续：可见损坏沿道路延伸，但仍是"一个局部段"
- 27分：影响呈中段连续：损坏在视野内无法一次看全起止，沿道路连续延伸
- 81分：影响呈长段/成片连续：沿线多点、多段同时受损

### I. 边坡排水（3/9/27/81）
- 3分：坡面干燥；无渗水、湿斑；排水沟/截水沟清晰、无淤堵迹象
- 9分：局部潮湿或零星渗水点；可见水迹但不连续；排水组织一般
- 27分：坡面普遍潮湿；渗水带明显；坡脚或沟内长期湿润/积水迹象；径流冲刷明显
- 81分：持续出水/流水痕明显；坡面长期饱水、泥化；排水失效特征突出

### J. 年降雨量（湿润度）（3/9/27/81）
- 3分：干旱/少雨区：年内强降雨事件少、持续湿润期短
- 9分：中等降水区：雨季明显但不极端，湿润期有限
- 27分：多雨/湿润区：强降雨较常见，长期湿润显著
- 81分：极湿/暴雨高发区：强降雨频繁且持续，水文触发条件长期具备

### K. 坡高/滑坡轴向尺度（3/9/27/81）
- 3分：小尺度：破坏体量小，后缘—前缘范围有限；单张照片可完整覆盖滑体关键边界
- 9分：中小尺度：滑体范围清晰但需要借助参照物才能看出其"明显大于局部修补"
- 27分：中大尺度：滑体/路基变形带呈连续条带，范围明显超出单点
- 81分：超大尺度：整体边坡—路基系统性失稳特征明显，属于"区域性/段落性"问题

### L. 冻融稳定性（3/9/27/81）
- 3分：稳定或无明显冻融影响：坡面整体完整，道路表面平顺
- 9分：轻度冻融不稳定：路面或坡脚出现零散、不连续的轻微起伏或不规则沉陷
- 27分：中等冻融不稳定：路面呈明显波浪状起伏，沉陷与隆起交替分布
- 81分：强烈冻融不稳定：大范围路基沉陷、明显波浪变形或塌陷坑

## 输出要求

1. 必须严格输出JSON格式，字段名必须与上述指标名称完全一致
2. 每个指标的打分必须是 3、9、27 或 81 之一
3. 请结合图像中的实际灾害特征和已提取的指标信息进行综合判断
4. 如果图像中无法明确判断某个指标，请根据已提取的指标信息进行合理推断

## 输出格式示例

{{
  "A 道路受影响程度": 27,
  "B 滑动/侵蚀效应": 9,
  "C 受影响道路长度": 27,
  "I 边坡排水": 81,
  "J 年降雨量（湿润度）": 27,
  "K 坡高/滑坡轴向尺度": 9,
  "L 冻融稳定性": 3
}}"""
        
        elif risk_type == "崩塌":
            user_prompt = f"""请根据图像和已提取的指标信息，按照FHWA标准对崩塌/落石（Rockfall）的各项风险指标进行打分。

{extracted_indicators}

## FHWA崩塌风险评价指标及打分标准

### D. 拦截有效性（3/9/27/81）
- 3分：拦石沟/拦石空间完整且清空良好；落石主要停留在沟内，路面几乎无落石迹象
- 9分：拦石沟存在但部分被填塞/尺度偏小；路面偶见落石或可见滚落通道
- 27分：拦石空间明显不足或维护差；路面经常可见块石、散落带直达路面
- 81分：无有效拦截条件：无沟/沟被完全填满/边坡直抵路缘，落石几乎必达路面

### F. 单次事件块体尺度（3/9/27/81）
- 3分：小块石为主：相对轮胎、标线宽度、护栏立柱等明显偏小；对通行影响有限
- 9分：中等块石：单块已足以造成轮胎/底盘风险，但仍可人工/小设备清理为主
- 27分：大块石：单块具有明显冲击危险，清理需机械；落石足以阻挡部分车道并诱发事故
- 81分：巨块/体积性块体：单块达到"显著阻断/致命冲击"的量级，或呈体积性崩落特征

### G. 对道路使用的影响（3/9/27/81）
- 3分：基本不影响通行：道路保持双向或正常通行状态，落石或堆积物主要位于路肩或边缘位置
- 9分：轻度影响通行：道路局部受限，存在临时清理痕迹、警示锥或限速标志
- 27分：显著影响通行：单车道或部分路段被阻断，需设置交通管制或临时绕行
- 81分：严重影响或中断通行：道路完全封闭或长期中断，需大规模清理或工程处置

### I. 边坡排水（3/9/27/81）
- 3分：坡面干燥；无渗水、湿斑；排水沟/截水沟清晰、无淤堵迹象
- 9分：局部潮湿或零星渗水点；可见水迹但不连续；排水组织一般
- 27分：坡面普遍潮湿；渗水带明显；坡脚或沟内长期湿润/积水迹象；径流冲刷明显
- 81分：持续出水/流水痕明显；坡面长期饱水、泥化；排水失效特征突出

### J. 年降雨量（湿润度）（3/9/27/81）
- 3分：前 365 日累计降水量 < 400 mm
- 9分：前 365 日累计降水量 400 – 800 mm
- 27分：前 365 日累计降水量 800 – 1200 mm
- 81分：前 365 日累计降水量 ≥ 1200 mm

### K. 坡高/崩塌影响尺度（3/9/27/81）
- 3分：小尺度：潜在不稳定区范围有限；单张照片可覆盖主要危险源位置与道路关系
- 9分：中小尺度：危险源清晰但需要参照物才能体现其"明显大于局部落石点"
- 27分：中大尺度：潜在失稳带呈连续分布，危险源不是单点，沿坡面具有明显延展性
- 81分：超大尺度：整体岩坡呈系统性危险带，存在多处潜在失稳源，对道路构成段落性威胁

### P. 结构条件（3/9/27/81）
- 3分：结构面不显著或总体"锁固"；难以形成自由块体
- 9分：结构面可见但取向杂乱，未见主导不利组合
- 27分：清晰不利结构面组控制块体边界（成组节理/层面），块体轮廓明显但贯通性一般
- 81分：主导不利结构面贯通明显，形成大量潜在可动块体或"成排剥落"趋势

## 输出要求

1. 必须严格输出JSON格式，字段名必须与上述指标名称完全一致
2. 每个指标的打分必须是 3、9、27 或 81 之一
3. 请结合图像中的实际灾害特征和已提取的指标信息进行综合判断
4. 如果图像中无法明确判断某个指标，请根据已提取的指标信息进行合理推断

## 输出格式示例

{{
  "D 拦截有效性": 27,
  "F 块体尺度": 9,
  "G 对道路使用的影响": 27,
  "I 边坡排水": 81,
  "J 年降雨量（湿润度）": 27,
  "K 坡高/影响尺度": 9,
  "P 结构条件": 3
}}"""
        
        else:
            # 未知类型，返回空结果
            return system_prompt, "无法识别风险类型，无法进行风险打分。"
        
        # 添加Few-shot示例
        if self.example_manager and self.example_manager.has_examples():
            examples = self.example_manager.get_examples_for_risk_scoring(risk_type=risk_type, max_examples=2)
            if examples:
                user_prompt += "\n\n## 参考示例（Few-shot Learning）\n"
                user_prompt += "以下是已标注的风险打分示例，请参考这些示例的打分结果：\n"
                for i, ex in enumerate(examples, 1):
                    formatted = self.example_manager.format_example_for_risk_scoring(ex)
                    user_prompt += f"\n示例{i}：{formatted['text']}\n"
                    # 提取关键指标得分
                    expected = formatted['expected_output']
                    key_scores = []
                    if risk_type == "滑坡":
                        for key in ["A 道路受影响程度", "B 滑动/侵蚀效应", "C 受影响道路长度"]:
                            if key in expected:
                                key_scores.append(f"{key}={expected[key]}")
                    elif risk_type == "崩塌":
                        for key in ["D 拦截有效性", "F 块体尺度", "G 对道路使用的影响"]:
                            if key in expected:
                                key_scores.append(f"{key}={expected[key]}")
                    if key_scores:
                        user_prompt += f"期望打分结果（部分指标）：{', '.join(key_scores)}\n"
        
        return system_prompt, user_prompt

    def _parse_risk_scores_json(self, text: str, risk_type: str) -> Dict[str, Any]:
        """
        从API响应中解析风险打分JSON
        """
        text = (text or "").strip()
        
        # 如果直接是JSON
        if text.startswith("{") and text.endswith("}"):
            try:
                result = json.loads(text)
                # 验证和规范化结果
                return self._normalize_risk_scores(result, risk_type)
            except:
                pass
        
        # 尝试提取JSON对象
        import re
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            try:
                result = json.loads(match.group(0))
                return self._normalize_risk_scores(result, risk_type)
            except:
                pass
        
        raise ValueError(f"无法从响应中提取JSON，响应前200字符：{text[:200]}")

    def _normalize_risk_scores(self, result: Dict[str, Any], risk_type: str) -> Dict[str, Any]:
        """
        规范化风险打分结果，确保所有指标都有值且为3/9/27/81之一
        """
        normalized = {}
        
        # 定义各类型需要的指标
        if risk_type == "滑坡":
            required_indicators = [
                "A 道路受影响程度",
                "B 滑动/侵蚀效应",
                "C 受影响道路长度",
                "I 边坡排水",
                "J 年降雨量（湿润度）",
                "K 坡高/滑坡轴向尺度",
                "L 冻融稳定性"
            ]
        elif risk_type == "崩塌":
            required_indicators = [
                "D 拦截有效性",
                "F 块体尺度",
                "G 对道路使用的影响",
                "I 边坡排水",
                "J 年降雨量（湿润度）",
                "K 坡高/影响尺度",
                "P 结构条件"
            ]
        else:
            return {}
        
        valid_scores = [3, 9, 27, 81]
        
        for indicator in required_indicators:
            value = result.get(indicator)
            if value is None:
                # 缺失时使用默认值9
                normalized[indicator] = 9
            else:
                try:
                    score = int(value)
                    if score in valid_scores:
                        normalized[indicator] = score
                    else:
                        # 无效值，使用默认值9
                        print(f"警告：指标 {indicator} 的打分 {score} 不在有效范围内（3/9/27/81），使用默认值9")
                        normalized[indicator] = 9
                except (ValueError, TypeError):
                    # 无法转换为整数，使用默认值9
                    print(f"警告：指标 {indicator} 的值 {value} 无法转换为有效打分，使用默认值9")
                    normalized[indicator] = 9
        
        return normalized

    def _compute_scores_local(self, record: Dict[str, Any], risk_type: str) -> Dict[str, Any]:
        """
        使用本地规则进行打分（向后兼容，当没有图像路径时使用）
        """
        risk_type = (risk_type or "").strip()
        scores: Dict[str, Any] = {}

        if risk_type == "滑坡":
            scores["A 道路受影响程度"] = self._score_landslide_A(record)
            scores["B 滑动/侵蚀效应"] = self._score_landslide_B(record)
            scores["C 受影响道路长度"] = self._score_landslide_C(record)
            scores["I 边坡排水"] = self._score_common_I(record, for_landslide=True)
            scores["J 年降雨量（湿润度）"] = self._score_landslide_J(record)
            scores["K 坡高/滑坡轴向尺度"] = self._score_landslide_K(record)
            scores["L 冻融稳定性"] = self._score_landslide_L(record)
        elif risk_type == "崩塌":
            scores["D 拦截有效性"] = self._score_rockfall_D(record)
            scores["F 块体尺度"] = self._score_rockfall_F(record)
            scores["G 对道路使用的影响"] = self._score_rockfall_G(record)
            scores["I 边坡排水"] = self._score_common_I(record, for_landslide=False)
            scores["J 年降雨量（湿润度）"] = self._score_rockfall_J(record)
            scores["K 坡高/影响尺度"] = self._score_rockfall_K(record)
            scores["P 结构条件"] = self._score_rockfall_P(record)
        else:
            # 未知类型时不打分
            pass

        return scores

    # ------------------ 滑坡相关赋分（本地规则，作为备用） ------------------
    @staticmethod
    def _score_landslide_A(record: Dict[str, Any]) -> int:
        """
        A. 道路受影响程度
        依据：裂缝发育、新鲜破坏、当前活动状态、变形发展阶段、工程扰动、防护类型。
        """
        crack = str(record.get("裂缝发育", "未知"))
        fresh = str(record.get("新鲜破坏", "未知"))
        activity = str(record.get("滑坡当前活动状态", record.get("当前活动状态", "未知")))
        stage = str(record.get("滑坡变形阶段", record.get("变形发展阶段", "未知")))
        disturb = str(record.get("工程扰动", "未知"))
        protect = str(record.get("防护类型", "未知"))

        if activity == "活动" and stage == "失稳阶段":
            return 81
        if fresh == "明显" and crack == "明显":
            return 81

        if activity in ("潜在活动", "活动"):
            return 27
        if crack == "明显" and fresh == "明显":
            return 27

        if crack == "少量" and fresh == "一般":
            return 9
        if disturb == "一般" and protect != "无":
            return 9

        if crack in ("无", "少量") and fresh == "无":
            return 3

        # 默认中等级别
        return 9

    @staticmethod
    def _score_landslide_B(record: Dict[str, Any]) -> int:
        """
        B. 滑动 / 侵蚀效应
        关联：裂缝发育、新鲜破坏、地貌单元、诱发因素、水对滑坡的控制作用、变形发展阶段。
        """
        crack = str(record.get("裂缝发育", "未知"))
        fresh = str(record.get("新鲜破坏", "未知"))
        landform = str(record.get("地貌单元", "未知"))
        trigger = str(record.get("诱发因素", ""))
        water_ctrl = str(record.get("滑坡水作用强度", record.get("水对滑坡的控制作用", "未知")))
        stage = str(record.get("滑坡变形阶段", record.get("变形发展阶段", "未知")))

        if landform == "沟谷" and any(t in trigger for t in ["河流侵蚀", "水事活动"]) and water_ctrl == "强":
            return 81
        if crack == "明显" and fresh == "明显" and stage == "加速变形":
            return 27

        if landform == "沟谷" and any(t in trigger for t in ["降雨", "河流侵蚀"]):
            return 9

        if crack in ("无", "少量") and fresh == "无":
            return 3

        return 9

    @staticmethod
    def _score_landslide_C(record: Dict[str, Any]) -> int:
        """
        C. 受影响道路长度
        主要关联：裂缝发育的连续性、变形发展阶段、当前活动状态。
        """
        crack = str(record.get("裂缝发育", "未知"))
        activity = str(record.get("滑坡当前活动状态", record.get("当前活动状态", "未知")))
        stage = str(record.get("滑坡变形阶段", record.get("变形发展阶段", "未知")))

        if stage == "失稳阶段" and activity == "活动":
            return 81
        if crack == "明显":
            return 27
        if crack in ("少量", "明显"):
            return 9
        if crack == "少量":
            return 3

        return 9

    @staticmethod
    def _score_landslide_J(record: Dict[str, Any]) -> int:
        """
        J. 年降雨量（湿润度）——滑坡（定性 + 诱发因素 + 排水状况）
        """
        trigger = str(record.get("诱发因素", ""))
        I_score = int(record.get("I 边坡排水", 9))
        water_ctrl = str(record.get("滑坡水作用强度", record.get("水对滑坡的控制作用", "未知")))

        has_rain = "降雨" in trigger

        if not has_rain:
            return 3

        if has_rain and I_score <= 9:
            return 9

        if has_rain and I_score >= 27:
            if water_ctrl == "强":
                return 81
            return 27

        return 9

    @staticmethod
    def _score_landslide_K(record: Dict[str, Any]) -> int:
        """
        K. 坡高 / 滑坡轴向尺度
        间接通过：变形发展阶段、裂缝发育、当前活动状态 来定性。
        """
        crack = str(record.get("裂缝发育", "未知"))
        fresh = str(record.get("新鲜破坏", "未知"))
        activity = str(record.get("滑坡当前活动状态", record.get("当前活动状态", "未知")))
        stage = str(record.get("滑坡变形阶段", record.get("变形发展阶段", "未知")))

        if stage == "失稳阶段" and activity == "活动":
            return 81
        if crack == "明显" and (stage == "加速变形" or fresh == "明显"):
            return 27
        if stage in ("初始变形", "加速变形") and fresh == "一般":
            return 9
        if stage == "初始变形" and crack in ("无", "少量"):
            return 3

        return 9

    @staticmethod
    def _score_landslide_L(record: Dict[str, Any]) -> int:
        """
        L. 冻融稳定性（寒区）
        关联：诱发因素是否包含"冻融"、裂缝发育、新鲜破坏、当前活动状态。
        """
        trigger = str(record.get("诱发因素", ""))
        crack = str(record.get("裂缝发育", "未知"))
        fresh = str(record.get("新鲜破坏", "未知"))
        activity = str(record.get("滑坡当前活动状态", record.get("当前活动状态", "未知")))

        has_freeze = "冻融" in trigger

        if not has_freeze:
            return 3

        if has_freeze and activity == "活动":
            return 81
        if has_freeze and crack == "明显":
            return 27
        if has_freeze and fresh == "一般" and crack == "少量":
            return 9

        return 9

    # ------------------ 崩塌 / 落石相关赋分（本地规则，作为备用） ------------------
    @staticmethod
    def _score_rockfall_D(record: Dict[str, Any]) -> int:
        """
        D. 拦截有效性（排水沟 / 拦石空间）
        关联：防护类型、落石传播可达性。
        """
        protect_type = str(record.get("防护类型", "未知"))
        reach = str(record.get("崩塌传播可达性", record.get("落石传播可达性", "未知")))

        if protect_type == "无" and reach == "易直达":
            return 81
        if reach == "易直达" and protect_type == "无":
            return 81
        if reach == "易直达" and protect_type != "无":
            return 27
        if protect_type in ("防护网", "挡墙/抗滑结构") and reach == "可能可达":
            return 9
        if protect_type != "无" and reach == "不可达":
            return 3

        return 9

    @staticmethod
    def _score_rockfall_F(record: Dict[str, Any]) -> int:
        """
        F. 单次事件块体尺度
        关联：对道路使用的影响、近期落石活动迹象、致灾形式。
        """
        use_score = int(record.get("G 对道路使用的影响", 9))
        recent = str(record.get("崩塌近期活动性", record.get("近期落石活动迹象", "未知")))
        disaster_form = str(record.get("崩塌致灾方式", record.get("对工程的致灾形式", "未知")))
        intercept_score = int(record.get("D 拦截有效性", 9))

        if use_score == 81 or intercept_score == 81:
            return 81
        if use_score >= 27 or disaster_form in ("撞击", "堆积掩埋"):
            return 27
        if use_score == 9 and recent == "偶发":
            return 9
        if use_score == 3 and recent in ("无", "偶发"):
            return 3

        return 9

    @staticmethod
    def _score_rockfall_G(record: Dict[str, Any]) -> int:
        """
        G. 对道路使用的影响
        关联：近期落石活动迹象、落石传播可达性、致灾形式、防护工程有效性。
        """
        recent = str(record.get("崩塌近期活动性", record.get("近期落石活动迹象", "未知")))
        reach = str(record.get("崩塌传播可达性", record.get("落石传播可达性", "未知")))
        protect_eff = str(record.get("崩塌防护有效性", record.get("防护工程有效性", "未知")))
        disaster_form = str(record.get("崩塌致灾方式", record.get("对工程的致灾形式", "未知")))

        if disaster_form == "堆积掩埋" and protect_eff == "低":
            return 81
        if reach == "易直达" and protect_eff in ("中", "低"):
            return 27
        if recent == "偶发" and reach == "可能可达":
            return 9
        if recent == "无" and reach in ("不可达", "可能可达"):
            return 3

        return 9

    @staticmethod
    def _score_common_I(record: Dict[str, Any], for_landslide: bool) -> int:
        """
        I. 边坡排水（滑坡 / 崩塌通用，但文本略有差异，这里统一成打分函数）。
        主要关联：防护类型中是否有"排水防护"、诱发因素是否为水相关、
        以及"水对滑坡的控制作用"或现场湿度（通过已有字段间接表达）。
        """
        protect_type = str(record.get("防护类型", "未知"))
        trigger = str(record.get("诱发因素", ""))
        water_ctrl = str(
            record.get(
                "滑坡水作用强度",
                record.get("水对滑坡的控制作用", "未知"),
            )
        )

        has_rain_or_river = any(t in trigger for t in ["降雨", "河流侵蚀", "水事活动"])

        if protect_type == "排水防护" and not has_rain_or_river:
            return 3

        if has_rain_or_river and water_ctrl == "中":
            return 9

        if has_rain_or_river and water_ctrl == "强":
            return 27 if for_landslide else 27

        if has_rain_or_river and water_ctrl == "强" and protect_type == "排水防护":
            # 文本中极端情况（强水控制 + 排水失效）对应 81
            return 81

        # 如果信息不足，给中等偏低分
        return 9

    @staticmethod
    def _score_rockfall_J(record: Dict[str, Any]) -> int:
        """
        J. 年降雨量（湿润度）——崩塌（定量判据：前 365 日累计降水量）。
        """
        val = record.get("降水_前365日_mm")
        try:
            total = float(val) if val is not None else None
        except (TypeError, ValueError):
            total = None

        if total is None:
            # 缺失时按中等处理
            return 9

        if total < 400:
            return 3
        if 400 <= total < 800:
            return 9
        if 800 <= total < 1200:
            return 27
        return 81

    @staticmethod
    def _score_rockfall_K(record: Dict[str, Any]) -> int:
        """
        K. 坡高 / 崩塌影响尺度
        关联：破碎程度、近期落石活动迹象、落石传播可达性。
        """
        broken = str(record.get("破碎程度", "未知"))
        recent = str(record.get("崩塌近期活动性", record.get("近期落石活动迹象", "未知")))
        reach = str(record.get("崩塌传播可达性", record.get("落石传播可达性", "未知")))

        if recent == "频繁" and reach == "易直达":
            return 81
        if broken == "极破碎" and recent == "频繁":
            return 27
        if recent in ("无", "偶发") and reach == "不可达":
            return 3

        return 9

    @staticmethod
    def _score_rockfall_P(record: Dict[str, Any]) -> int:
        """
        P. 结构条件（Case 1）
        关联：破碎程度、裂缝发育、落石传播可达性。
        """
        broken = str(record.get("破碎程度", "未知"))
        crack = str(record.get("裂缝发育", "未知"))
        reach = str(record.get("崩塌传播可达性", record.get("落石传播可达性", "未知")))

        if broken == "完整" and crack in ("无", "少量"):
            return 3
        if broken == "较破碎" and crack == "少量":
            return 9
        if crack == "明显" and broken in ("较破碎", "极破碎"):
            return 27
        if broken == "极破碎" and reach == "易直达":
            return 81

        return 9

    # ------------------------------------------------------------------
    # 二、风险“评价过程”层：在各指标得分基础上汇总为总分 / 指数 / 等级
    # ------------------------------------------------------------------
    @staticmethod
    def aggregate_risk(indicator_scores: Dict[str, Any], risk_type: str) -> Dict[str, Any]:
        """
        根据指标得分计算：
        - 风险评价总分（各指标得分直接求和）；
        - 风险指数（按最大可能值归一化到 0-100）；
        - 风险等级（低 / 中 / 高 / 极高）。
        """
        # 只统计数值型得分
        numeric_scores = [int(v) for v in indicator_scores.values() if isinstance(v, (int, float))]
        total_score = sum(numeric_scores) if numeric_scores else 0

        # 最大可能得分：每个指标最高 81 分
        max_per_indicator = 81
        num_indicators = len(numeric_scores) if numeric_scores else 1
        max_total = max_per_indicator * num_indicators

        risk_index = 0.0
        if max_total > 0:
            risk_index = (total_score / max_total) * 100.0

        level = RiskAssessment._determine_risk_level(risk_index)

        return {
            "风险评价总分": total_score,
            "风险指数": round(risk_index, 2),
            "风险等级": level,
        }

    @staticmethod
    def _determine_risk_level(risk_index: float) -> str:
        """
        根据 0-100 风险指数划分等级：
        <25  低风险；
        25-50 中风险；
        50-75 高风险；
        >=75 极高风险。
        """
        if risk_index < 25:
            return "低风险"
        if risk_index < 50:
            return "中风险"
        if risk_index < 75:
            return "高风险"
        return "极高风险"

    # ------------------------------------------------------------------
    # 三、Excel 输出
    # ------------------------------------------------------------------
    def _get_sheet_name(self, record: Dict[str, Any]) -> str:
        """
        根据记录的风险类型获取对应的sheet名称
        
        Args:
            record: 记录字典
            
        Returns:
            sheet名称
        """
        risk_type = record.get("灾害类型", record.get("风险类型", "")).strip()
        if risk_type == "滑坡":
            return "滑坡"
        elif risk_type == "崩塌":
            return "崩塌"
        else:
            return "未分类"
    
    def _save_result_to_excel(self, risk_result: Dict[str, Any]) -> None:
        """
        将单条风险评价结果追加保存到专用 Excel，根据灾害类型自动分类到不同的sheet。

        列包括：
        - 灾害编号
        - 灾害类型
        - 各指标风险得分（A/B/C/... 或 D/F/G/... 等）
        - 风险评价总分
        - 风险指数
        - 风险等级
        """
        row = dict(risk_result)  # 复制一份，避免外部引用被修改
        
        # 获取对应的sheet名称
        sheet_name = self._get_sheet_name(row)
        risk_type = row.get("灾害类型", row.get("风险类型", "未知"))
        
        # 将记录转换为DataFrame
        df_new = pd.DataFrame([row])
        
        # 读取现有Excel文件的所有sheet（如果存在）
        existing_sheets = {}
        if self.output_path.exists():
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
        with pd.ExcelWriter(self.output_path, engine="openpyxl", mode="w") as writer:
            for sheet, df in existing_sheets.items():
                df.to_excel(writer, sheet_name=sheet, index=False)
        
        print(f"风险评价数据已保存到: {self.output_path} (Sheet: {sheet_name}, 灾害类型: {risk_type})")


if __name__ == "__main__":
    # 简单自测（可根据需要扩展）
    ra = RiskAssessment()
    demo = {
        "编号": "A1",
        "风险类型": "滑坡",
        "裂缝发育": "明显",
        "新鲜破坏": "明显",
        "滑坡当前活动状态": "活动",
        "滑坡变形阶段": "失稳阶段",
        "诱发因素": "降雨;切坡",
        "防护类型": "排水防护",
        "滑坡水作用强度": "强",
        "降水_前365日_mm": 900,
    }
    print(ra.assess_risk(demo))
