# -*- coding: utf-8 -*-
"""
模块3.3：图像语义理解与地质判识模块（AI核心）
功能定位：基于照片可见信息，对灾害类型、地质条件等进行规范化辅助判识
支持多个大模型API
"""
import base64
import json
import re
from typing import Dict, Any, Optional, List
from openai import OpenAI
from modules.indicator_standards import IndicatorStandards


class AIExtractor:
    """AI图像语义理解与地质判识提取器"""
    
    def __init__(self, model_provider: str = "openai", model_name: str = None, 
                 example_manager=None):
        """
        初始化AI提取器
        
        Args:
            model_provider: 模型提供商（如"openai"）
            model_name: 模型名称，如果为None则使用默认模型
            example_manager: Few-shot示例管理器，如果为None则自动初始化
        """
        from config import MODEL_CONFIGS, DEFAULT_MODEL_PROVIDER, DEFAULT_MODEL_NAME
        
        self.model_provider = model_provider or DEFAULT_MODEL_PROVIDER
        self.model_config = MODEL_CONFIGS.get(self.model_provider, {})
        
        if model_name is None:
            model_name = DEFAULT_MODEL_NAME
        self.model_name = model_name
        
        # 初始化指标标准体系
        self.standards = IndicatorStandards()
        
        # 初始化Few-shot示例管理器
        if example_manager is None:
            try:
                from modules.few_shot_examples import FewShotExampleManager
                self.example_manager = FewShotExampleManager()
                if self.example_manager.has_examples():
                    print(f"Few-shot Learning已启用，加载了 {len(self.example_manager.examples)} 个示例")
                else:
                    print("Few-shot Learning未启用（测试集为空）")
            except Exception as e:
                print(f"初始化Few-shot示例管理器失败: {e}，将不使用Few-shot Learning")
                self.example_manager = None
        else:
            self.example_manager = example_manager
        
        # 初始化客户端
        self.client = self._init_client()
    
    def _init_client(self) -> Any:
        """初始化API客户端"""
        # 所有模型都使用OpenAI兼容格式（通过API网关）
        if self.model_provider in ["openai", "gemini", "anthropic", "grok", "qwen"]:
            import httpx
            timeout = self.model_config.get("timeout", 300)  # 默认300秒
            return OpenAI(
                api_key=self.model_config.get("api_key"),
                base_url=self.model_config.get("base_url"),
                timeout=httpx.Timeout(timeout, connect=30)  # 连接超时30秒，总超时300秒
            )
        else:
            raise ValueError(f"不支持的模型提供商: {self.model_provider}")
    
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
    
    def _extract_json_from_response(self, text: str) -> Dict[str, Any]:
        """
        从模型响应中提取JSON对象
        容错处理：如果响应中包含多余文字，尝试提取JSON部分
        """
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
        
        text = (text or "").strip()
        debug_log("ai_extraction.py:76", "extracting JSON from response", {"text_length":len(text),"text_preview":text[:200]}, "B")
        
        # 如果直接是JSON
        if text.startswith("{") and text.endswith("}"):
            try:
                result = json.loads(text)
                debug_log("ai_extraction.py:82", "JSON parsed successfully", {"keys":list(result.keys()) if isinstance(result,dict) else "not_dict","诱发因素":result.get("诱发因素") if isinstance(result,dict) else None,"威胁对象":result.get("威胁对象") if isinstance(result,dict) else None}, "B")
                # 处理多选字段：统一转换为分号分隔的字符串
                result = self._normalize_multi_select_fields(result)
                return result
            except:
                pass
        
        # 尝试提取JSON对象
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            try:
                result = json.loads(match.group(0))
                debug_log("ai_extraction.py:91", "JSON extracted and parsed", {"keys":list(result.keys()) if isinstance(result,dict) else "not_dict","诱发因素":result.get("诱发因素") if isinstance(result,dict) else None,"威胁对象":result.get("威胁对象") if isinstance(result,dict) else None}, "B")
                # 处理多选字段：统一转换为分号分隔的字符串
                result = self._normalize_multi_select_fields(result)
                return result
            except:
                pass
        
        raise ValueError(f"无法从响应中提取JSON，响应前200字符：{text[:200]}")
    
    def _normalize_multi_select_fields(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        规范化多选字段：统一转换为分号分隔的字符串
        
        Args:
            result: AI返回的结果字典
            
        Returns:
            规范化后的结果字典
        """
        multi_select_fields = ["诱发因素", "威胁对象", "防护类型"]
        
        for field in multi_select_fields:
            if field in result:
                value = result[field]
                if value is None:
                    continue
                
                # 如果是列表，转换为分号分隔的字符串
                if isinstance(value, list):
                    # 过滤掉空值
                    filtered = [str(v).strip() for v in value if v and str(v).strip()]
                    if filtered:
                        result[field] = ";".join(filtered)
                    else:
                        # 如果过滤后为空，删除该字段（不设置默认值）
                        del result[field]
                # 如果是字符串
                elif isinstance(value, str):
                    # 如果包含逗号，转换为分号
                    if "," in value:
                        # 分割并清理
                        parts = [p.strip() for p in value.split(",") if p.strip()]
                        if parts:
                            result[field] = ";".join(parts)
                        else:
                            # 如果分割后为空，删除该字段
                            del result[field]
                    # 如果已经是分号分隔，保持不变
                    elif ";" in value:
                        # 清理并重新组合
                        parts = [p.strip() for p in value.split(";") if p.strip()]
                        if parts:
                            result[field] = ";".join(parts)
                        else:
                            # 如果分割后为空，删除该字段
                            del result[field]
                    # 单个值，保持不变
                    else:
                        if value.strip() == "":
                            # 如果为空，删除该字段
                            del result[field]
        
        return result
    
    def extract_indicators(self, image_path: str) -> Dict[str, Any]:
        """
        从图片中提取所有指标（两阶段识别，FHWA框架）
        
        第一阶段：识别风险类型（滑坡、崩塌）
        第二阶段：根据风险类型，识别对应的细分类型和通用指标
        
        Args:
            image_path: 图片路径
            
        Returns:
            包含所有指标值的字典
        """
        # ========== 第一阶段：识别风险类型 ==========
        print("阶段1：识别风险类型...")
        risk_type = self._extract_risk_type(image_path)
        
        # ========== 第二阶段：根据风险类型识别细分类型和通用指标 ==========
        print(f"阶段2：根据风险类型({risk_type})识别细分类型和通用指标...")
        detailed_indicators = self._extract_detailed_indicators(image_path, risk_type)
        
        # 合并结果
        result = {"风险类型": risk_type}
        result.update(detailed_indicators)
        
        # 最终规范化：只保留相关指标，不输出不相关的指标
        return self._normalize_final_result(result, risk_type)
    
    def _extract_risk_type(self, image_path: str) -> str:
        """
        第一阶段：识别风险类型（FHWA框架）
        
        Args:
            image_path: 图片路径
            
        Returns:
            风险类型（滑坡、崩塌）
        """
        system_prompt = """你是地质灾害图片识别专家。
你必须只输出严格 JSON，不要任何解释、不要 Markdown、不要多余文字。
请仔细分析图片特征，根据判识依据选择最符合的选项。"""
        
        user_prompt = """请根据图片识别地质灾害的风险类型（FHWA框架）。

## 风险类型识别标准

**滑坡（Landslide，含 Debris Flow）**：满足以下特征之一或多个
- ① 斜坡体或沟谷内土体、岩体或其混合体发生整体或局部位移
- ② 可见拉张裂缝、剪出口、滑移带或流动痕迹
- ③ 物质可呈块状滑移、旋转滑动或流动状态
- ④ 运动方向与坡向或沟谷轴线一致
- ⑤ 若表现为沟谷内高速流动、泥砂与块石混杂、伴随冲刷与冲淤扇，则判定为泥石流型滑坡（Debris Flow）

**崩塌（Rockfall）**：满足以下特征之一或多个
- ① 陡峻坡面、岩壁或高切坡
- ② 岩块或岩体自高处脱离母体发生坠落、翻滚或跳跃
- ③ 常见卸荷裂隙、陡坎、节理面控制
- ④ 坠落路径清晰，运动以自由落体或滚动为主

## 输出要求

只输出JSON格式，字段名为"风险类型"，值为：滑坡 或 崩塌

如果图片中无法明确判断，请根据主要特征选择最接近的类型。

示例：
{"风险类型": "滑坡"}"""
        
        # 添加Few-shot示例
        few_shot_content = []
        if self.example_manager and self.example_manager.has_examples():
            examples = self.example_manager.get_examples_for_extraction(max_examples=2)
            if examples:
                user_prompt += "\n\n## 参考示例（Few-shot Learning）\n"
                user_prompt += "以下是已标注的示例，请参考这些示例的识别结果：\n"
                for i, ex in enumerate(examples, 1):
                    formatted = self.example_manager.format_example_for_extraction(ex)
                    user_prompt += f"\n示例{i}：{formatted['text']}\n"
                    user_prompt += f"期望输出：{{\"风险类型\": \"{formatted['expected_output'].get('灾害类型', '未知')}\"}}\n"
        
        try:
            if self.model_provider in ["openai", "gemini", "anthropic", "grok", "qwen"]:
                # 调用API提取风险类型
                data_url = self._image_to_data_url(image_path)
                
                # 添加重试机制和总时长控制
                import time
                max_retries = 2  # 重试次数
                retry_delay = 5  # 单次重试间隔（秒）
                # 单步（风险类型识别阶段）总时间上限（秒），默认与全局 timeout 一致
                step_timeout = self.model_config.get("timeout", 300)
                step_start_time = time.time()
                
                result = None
                last_error = None
                
                for attempt in range(max_retries):
                    # 检查本阶段累计耗时，确保不超过 step_timeout
                    elapsed_step = time.time() - step_start_time
                    if elapsed_step > step_timeout:
                        print(f"风险类型识别阶段总耗时已超过 {step_timeout} 秒，停止重试")
                        if last_error:
                            raise last_error
                        raise TimeoutError(f"风险类型识别阶段超时（>{step_timeout}秒）")
                    try:
                        print(f"正在调用API识别风险类型（尝试 {attempt + 1}/{max_retries}）...")
                        print(f"[API请求] System Prompt: {system_prompt[:200]}..." if len(system_prompt) > 200 else f"[API请求] System Prompt: {system_prompt}")
                        print(f"[API请求] User Prompt长度: {len(user_prompt)} 字符")
                        print(f"[API请求] 模型: {self.model_name}")
                        start_time = time.time()
                        
                        # 构建消息内容（包含Few-shot示例图片）
                        user_content = [{"type": "text", "text": user_prompt}]
                        
                        # 添加Few-shot示例图片
                        if self.example_manager and self.example_manager.has_examples():
                            examples = self.example_manager.get_examples_for_extraction(max_examples=2)
                            for ex in examples:
                                formatted = self.example_manager.format_example_for_extraction(ex)
                                if formatted.get("image"):
                                    user_content.append({
                                        "type": "image_url",
                                        "image_url": {"url": formatted["image"]}
                                    })
                        
                        # 添加待识别的图片
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
                        print(f"风险类型识别API调用完成，耗时: {elapsed_time:.2f} 秒")
                        
                        # 检查响应对象（标准OpenAI格式）
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
                        
                        result = self._extract_json_from_response(raw_text)
                        break  # 成功，跳出重试循环
                        
                    except Exception as e:
                        last_error = e
                        elapsed_time = time.time() - start_time if 'start_time' in locals() else 0
                        print(f"风险类型识别API调用失败（尝试 {attempt + 1}/{max_retries}，耗时 {elapsed_time:.2f} 秒）: {e}")
                        
                        if attempt < max_retries - 1:
                            # 再次检查剩余可用时间，避免总时长超过 step_timeout
                            now = time.time()
                            elapsed_step = now - step_start_time
                            remaining = step_timeout - elapsed_step
                            if remaining <= 0:
                                print(f"风险类型识别阶段剩余时间不足（{remaining:.2f} 秒），不再重试")
                                raise last_error
                            
                            sleep_time = min(retry_delay, max(0, remaining))
                            print(f"等待 {sleep_time:.2f} 秒后重试...（本阶段剩余可用时间约 {remaining:.2f} 秒）")
                            time.sleep(sleep_time)
                        else:
                            print(f"所有重试均失败，最后错误: {last_error}")
                            raise last_error
                
                # 确保result已定义
                if result is None:
                    raise ValueError(f"API调用失败，无法获取结果。最后错误: {last_error}")
                
                risk_type = result.get("风险类型", None)
                # 验证风险类型是否有效
                valid_types = ["滑坡", "崩塌"]
                if risk_type not in valid_types:
                    print(f"警告：识别出的风险类型 '{risk_type}' 不在有效范围内，使用默认值'滑坡'")
                    return "滑坡"  # 默认返回"滑坡"
                return risk_type
            else:
                raise ValueError(f"不支持的模型提供商: {self.model_provider}")
        except Exception as e:
            print(f"风险类型识别失败: {e}，使用默认值'滑坡'")
            import traceback
            traceback.print_exc()  # 打印详细错误信息
            return "滑坡"  # 默认返回"滑坡"
    
    def _extract_detailed_indicators(self, image_path: str, risk_type: str) -> Dict[str, Any]:
        """
        第二阶段：根据风险类型识别细分类型和通用指标
        
        Args:
            image_path: 图片路径
            risk_type: 风险类型（滑坡、崩塌、泥石流、其他）
            
        Returns:
            包含细分类型和通用指标的字典
        """
        system_prompt = """你是地质灾害图片信息抽取助手。
你必须只输出严格 JSON，不要任何解释、不要 Markdown、不要多余文字。
请仔细分析图片特征，根据判识依据选择最符合的选项。"""
        
        # 根据风险类型生成对应的Prompt
        user_prompt = self.standards.generate_prompt_template_by_type(risk_type)
        
        # 添加Few-shot示例
        if self.example_manager and self.example_manager.has_examples():
            examples = self.example_manager.get_examples_for_extraction(risk_type=risk_type, max_examples=2)
            if examples:
                user_prompt += "\n\n## 参考示例（Few-shot Learning）\n"
                user_prompt += "以下是已标注的示例，请参考这些示例的识别结果：\n"
                for i, ex in enumerate(examples, 1):
                    formatted = self.example_manager.format_example_for_extraction(ex)
                    # 提取关键指标作为示例
                    expected = formatted['expected_output']
                    key_indicators = []
                    if "坡度" in expected:
                        key_indicators.append(f"坡度={expected['坡度']}")
                    if "物质类型" in expected:
                        key_indicators.append(f"物质类型={expected['物质类型']}")
                    if "破碎程度" in expected:
                        key_indicators.append(f"破碎程度={expected['破碎程度']}")
                    if key_indicators:
                        user_prompt += f"\n示例{i}：{formatted['text']}\n"
                        user_prompt += f"期望输出关键指标：{', '.join(key_indicators)}\n"
        
        try:
            if self.model_provider in ["openai", "gemini", "anthropic", "grok", "qwen"]:
                # 调用API提取详细指标
                data_url = self._image_to_data_url(image_path)
                
                # 添加重试机制，并限制单步总时长
                import time
                max_retries = 3
                retry_delay = 2
                step_timeout = self.model_config.get("timeout", 300)
                step_start_time = time.time()
                
                result = None
                last_error = None
                
                for attempt in range(max_retries):
                    # 检查本阶段累计耗时，确保不超过 step_timeout
                    elapsed_step = time.time() - step_start_time
                    if elapsed_step > step_timeout:
                        print(f"详细指标提取阶段总耗时已超过 {step_timeout} 秒，停止重试")
                        if last_error:
                            raise last_error
                        raise TimeoutError(f"详细指标提取阶段超时（>{step_timeout}秒）")
                    try:
                        print(f"正在调用API提取详细指标（尝试 {attempt + 1}/{max_retries}）...")
                        print(f"[API请求] System Prompt: {system_prompt[:200]}..." if len(system_prompt) > 200 else f"[API请求] System Prompt: {system_prompt}")
                        print(f"[API请求] User Prompt长度: {len(user_prompt)} 字符")
                        print(f"[API请求] 模型: {self.model_name}")
                        start_time = time.time()
                        
                        # 构建消息内容（包含Few-shot示例图片）
                        user_content = [{"type": "text", "text": user_prompt}]
                        
                        # 添加Few-shot示例图片
                        if self.example_manager and self.example_manager.has_examples():
                            examples = self.example_manager.get_examples_for_extraction(risk_type=risk_type, max_examples=2)
                            for ex in examples:
                                formatted = self.example_manager.format_example_for_extraction(ex)
                                if formatted.get("image"):
                                    user_content.append({
                                        "type": "image_url",
                                        "image_url": {"url": formatted["image"]}
                                    })
                        
                        # 添加待识别的图片
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
                        print(f"详细指标提取API调用完成，耗时: {elapsed_time:.2f} 秒")
                        
                        # 检查响应对象（标准OpenAI格式）
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
                        
                        result = self._extract_json_from_response(raw_text)
                        print(f"[API解析] 解析后的JSON键: {list(result.keys()) if result else 'None'}")
                        break  # 成功，跳出重试循环
                        
                    except Exception as e:
                        last_error = e
                        if attempt < max_retries - 1:
                            print(f"API调用失败（尝试 {attempt + 1}/{max_retries}）: {e}")
                            # 再次检查剩余可用时间，避免总时长超过 step_timeout
                            now = time.time()
                            elapsed_step = now - step_start_time
                            remaining = step_timeout - elapsed_step
                            if remaining <= 0:
                                print(f"详细指标提取阶段剩余时间不足（{remaining:.2f} 秒），不再重试")
                                raise last_error
                            
                            sleep_time = min(retry_delay, max(0, remaining))
                            print(f"等待 {sleep_time:.2f} 秒后重试...（本阶段剩余可用时间约 {remaining:.2f} 秒）")
                            time.sleep(sleep_time)
                        else:
                            raise e  # 最后一次尝试失败，抛出异常
                
                # 确保result已定义
                if result is None:
                    raise ValueError("API调用失败，无法获取结果")
                
                # 规范化结果（只规范化提取到的指标，不要求所有指标）
                return self._normalize_partial_result(result, risk_type)
            else:
                raise ValueError(f"不支持的模型提供商: {self.model_provider}")
        except Exception as e:
            print(f"详细指标提取失败: {e}，返回默认值")
            import traceback
            traceback.print_exc()  # 打印详细错误堆栈
            return self._get_partial_default_result(risk_type)
    
    def _extract_with_openai(self, image_path: str, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """使用OpenAI API提取指标"""
        data_url = self._image_to_data_url(image_path)
        
        try:
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
                        "content": [
                            {
                                "type": "text",
                                "text": user_prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": data_url
                                }
                            }
                        ]
                    }
                ],
            )
            
            # 检查响应对象（标准OpenAI格式）
            if hasattr(resp, 'choices') and resp.choices:
                raw_text = resp.choices[0].message.content
            elif hasattr(resp, 'output_text'):
                raw_text = (resp.output_text or "").strip()
            else:
                raw_text = ""
            
            result = self._extract_json_from_response(raw_text)
            
            # 验证和规范化结果
            return self._normalize_result(result)
            
        except Exception as e:
            # 如果提取失败，返回所有字段为"未知"
            print(f"AI提取失败: {e}")
            return self._get_default_result()
    
    def _normalize_final_result(self, result: Dict[str, Any], risk_type: str) -> Dict[str, Any]:
        """
        最终规范化提取结果，只保留相关指标
        
        Args:
            result: 合并后的提取结果
            risk_type: 风险类型（滑坡或崩塌）
            
        Returns:
            规范化后的结果（只包含相关指标）
        """
        normalized = {}
        all_standards_dict = self.standards.get_all_indicators()
        
        # 确定需要保留的指标列表
        indicators_to_keep = []
        
        # 1. 风险类型（必须）
        indicators_to_keep.append("风险类型")
        
        # 2. 根据风险类型添加特定指标
        if risk_type == "滑坡":
            indicators_to_keep.extend([
                "滑坡破坏方式",
                "滑坡当前活动状态",
                "滑坡变形阶段",
                "滑坡水作用强度",
                "滑坡致灾方式",
            ])
        elif risk_type == "崩塌":
            indicators_to_keep.extend([
                "崩塌类型",
                "崩塌近期活动性",
                "崩塌传播可达性",
                "崩塌防护有效性",
                "崩塌致灾方式",
            ])
        
        # 3. 通用指标（所有类型都需要）
        indicators_to_keep.extend([
            "坡度等级",
            "地貌单元",
            "物质类型",
            "破碎程度",
            "风化程度",
            "植被覆盖",
            "裂缝发育",
            "新鲜破坏",
            "工程扰动",
            "防护类型",
            "诱发因素",
            "威胁对象",
        ])
        
        # 4. 基础信息（如果有）
        if "编号" in result:
            indicators_to_keep.append("编号")
        if "纬度" in result:
            indicators_to_keep.extend(["纬度", "经度", "高程_m", "拍摄日期"])
        
        # 5. 外部环境数据（如果有）
        external_indicators = [k for k in result.keys() if k.startswith("降水_") or k.startswith("地震") or k.startswith("坡度_")]
        indicators_to_keep.extend(external_indicators)
        
        # 只保留相关指标
        for indicator_name in indicators_to_keep:
            if indicator_name in all_standards_dict or indicator_name in result:
                value = result.get(indicator_name)
                
                # 如果值为None或空，使用默认值（第一个有效选项）
                if value is None or (isinstance(value, str) and value.strip() == ""):
                    # 获取默认值（第一个有效选项）
                    default_value = self._get_default_value_for_indicator(indicator_name, risk_type)
                    if default_value:
                        normalized[indicator_name] = default_value
                    # 如果没有默认值，跳过该指标
                else:
                    # 如果是指标标准体系中的指标，验证值是否符合规范
                    if indicator_name in all_standards_dict:
                        # #region agent log
                        import json as json_module
                        import os
                        log_path = r"d:\地质灾害一张图\.cursor\debug.log"
                        def debug_log(location, message, data, hypothesis_id):
                            try:
                                with open(log_path, 'a', encoding='utf-8') as f:
                                    f.write(json_module.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":hypothesis_id,"location":location,"message":message,"data":data,"timestamp":int(__import__('time').time()*1000)})+"\n")
                            except: pass
                        is_multi = all_standards_dict[indicator_name].get("多选", False)
                        debug_log("ai_extraction.py:456", "validating indicator", {"indicator_name":indicator_name,"value":value,"value_type":type(value).__name__,"is_multi":is_multi}, "B")
                        # #endregion
                        
                        if self.standards.validate_indicator_value(indicator_name, value, risk_type):
                            normalized[indicator_name] = value
                            debug_log("ai_extraction.py:460", "indicator validated and set", {"indicator_name":indicator_name,"final_value":value,"final_value_type":type(value).__name__}, "B")
                        else:
                            # 验证失败，使用默认值
                            default_value = self._get_default_value_for_indicator(indicator_name, risk_type)
                            print(f"警告：指标 {indicator_name} 的值 {value} 不符合规范，已设为默认值: {default_value}")
                            if default_value:
                                normalized[indicator_name] = default_value
                            debug_log("ai_extraction.py:464", "indicator validation failed", {"indicator_name":indicator_name,"original_value":value,"default_value":default_value}, "B")
                    else:
                        # 非标准指标（如基础信息、外部数据），直接使用
                        normalized[indicator_name] = value
        
        return normalized
    
    def _normalize_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        规范化提取结果（保留用于兼容性）
        
        Args:
            result: 原始提取结果
            
        Returns:
            规范化后的结果
        """
        risk_type = result.get("风险类型", "未知")
        return self._normalize_final_result(result, risk_type)
    
    def _normalize_partial_result(self, result: Dict[str, Any], risk_type: str) -> Dict[str, Any]:
        """
        规范化部分提取结果（第二阶段使用）
        只规范化当前风险类型相关的指标
        
        Args:
            result: 原始提取结果
            risk_type: 风险类型
            
        Returns:
            规范化后的结果
        """
        normalized = {}
        
        # 确定需要规范化的指标列表
        indicators_to_check = []
        
        if risk_type == "滑坡":
            indicators_to_check.extend([
                "滑坡破坏方式",
                "滑坡当前活动状态",
                "滑坡变形阶段",
                "滑坡水作用强度",
                "滑坡致灾方式",
            ])
        elif risk_type == "崩塌":
            indicators_to_check.extend([
                "崩塌类型",
                "崩塌近期活动性",
                "崩塌传播可达性",
                "崩塌防护有效性",
                "崩塌致灾方式",
            ])
        
        # 通用指标
        indicators_to_check.extend([
            "坡度等级",
            "地貌单元",
            "物质类型",
            "破碎程度",
            "风化程度",
            "植被覆盖",
            "裂缝发育",
            "新鲜破坏",
            "工程扰动",
            "防护类型",
            "诱发因素",
            "威胁对象",
        ])
        
        # 规范化提取到的指标
        all_standards_dict = self.standards.get_all_indicators()  # 获取所有指标的字典
        
        for indicator_name in indicators_to_check:
            if indicator_name in all_standards_dict:
                value = result.get(indicator_name)
                
                # 如果值为None或空，使用默认值（第一个有效选项）
                if value is None or (isinstance(value, str) and value.strip() == ""):
                    # 获取默认值（第一个有效选项）
                    default_value = self._get_default_value_for_indicator(indicator_name, risk_type)
                    if default_value:
                        normalized[indicator_name] = default_value
                    # 如果没有默认值，跳过该指标
                else:
                    # 验证值是否符合规范
                    if self.standards.validate_indicator_value(indicator_name, value, risk_type):
                        normalized[indicator_name] = value
                    else:
                        # 验证失败，使用默认值
                        default_value = self._get_default_value_for_indicator(indicator_name, risk_type)
                        print(f"警告：指标 {indicator_name} 的值 {value} 不符合规范，已设为默认值: {default_value}")
                        if default_value:
                            normalized[indicator_name] = default_value
            # 注意：不在indicators_to_check中的指标不会被添加到normalized中
        
        return normalized
    
    def _get_default_value_for_indicator(self, indicator_name: str, risk_type: str = None) -> str:
        """获取指标的默认值（第一个有效选项）"""
        all_indicators = self.standards.get_all_indicators()
        if indicator_name not in all_indicators:
            return None
        
        standard = all_indicators[indicator_name]
        allowed_values = standard.get("取值规则", [])
        
        # 特殊处理：崩塌类型的物质类型
        if indicator_name == "物质类型" and risk_type == "崩塌":
            allowed_values = ["岩质", "土岩混合"]
        
        # 返回第一个有效选项
        if allowed_values:
            return allowed_values[0]
        return None
    
    def _get_partial_default_result(self, risk_type: str) -> Dict[str, Any]:
        """获取部分默认结果（第二阶段使用）"""
        result = {}
        
        # 根据风险类型设置默认值
        if risk_type == "滑坡":
            indicators = [
                "滑坡破坏方式",
                "滑坡当前活动状态",
                "滑坡变形阶段",
                "滑坡水作用强度",
                "滑坡致灾方式",
            ]
        elif risk_type == "崩塌":
            indicators = [
                "崩塌类型",
                "崩塌近期活动性",
                "崩塌传播可达性",
                "崩塌防护有效性",
                "崩塌致灾方式",
            ]
        else:
            indicators = []
        
        for indicator_name in indicators:
            default_value = self._get_default_value_for_indicator(indicator_name, risk_type)
            if default_value:
                result[indicator_name] = default_value
        
        # 通用指标默认值
        common_indicators = [
            "坡度等级",
            "地貌单元",
            "物质类型",
            "破碎程度",
            "风化程度",
            "植被覆盖",
            "裂缝发育",
            "新鲜破坏",
            "工程扰动",
            "防护类型",
            "诱发因素",
            "威胁对象",
        ]
        
        for indicator_name in common_indicators:
            default_value = self._get_default_value_for_indicator(indicator_name, risk_type)
            if default_value:
                result[indicator_name] = default_value
        
        return result
    
    def _get_default_result(self) -> Dict[str, Any]:
        """获取默认结果（所有字段使用第一个有效选项）"""
        result = {}
        all_indicators = self.standards.get_all_indicators()
        for name in all_indicators.keys():
            default_value = self._get_default_value_for_indicator(name)
            if default_value:
                result[name] = default_value
        return result
    
    def extract_with_multiple_models(self, image_path: str, model_names: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        使用多个模型提取指标，用于对比
        
        Args:
            image_path: 图片路径
            model_names: 模型名称列表
            
        Returns:
            {模型名称: 提取结果} 字典
        """
        results = {}
        original_model = self.model_name
        
        for model in model_names:
            try:
                self.model_name = model
                self.client = self._init_client()  # 重新初始化客户端
                result = self.extract_indicators(image_path)
                results[model] = result
            except Exception as e:
                print(f"模型 {model} 提取失败: {e}")
                results[model] = self._get_default_result()
        
        # 恢复原始模型
        self.model_name = original_model
        self.client = self._init_client()
        
        return results


if __name__ == "__main__":
    # 测试代码
    extractor = AIExtractor(model_provider="openai", model_name="gpt-5-nano-2025-08-07")
    test_image = r"C:\Users\UCD-K\Desktop\科研工作\文章撰写-AI赋能地质调查\地质调查一张图\图片测试\A1.jpg"
    result = extractor.extract_indicators(test_image)
    print(json.dumps(result, ensure_ascii=False, indent=2))
