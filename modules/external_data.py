# -*- coding: utf-8 -*-
"""
模块3.4：外部环境数据补充模块
功能定位：基于拍摄时间与空间位置，补充与灾害演化密切相关的背景环境数据
"""
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import requests
from config import EXTERNAL_DATA_CONFIG


class ExternalDataSupplement:
    """外部环境数据补充类"""
    
    def __init__(self):
        self.config = EXTERNAL_DATA_CONFIG
    
    def supplement_all(self, latitude: float, longitude: float, shooting_date: str) -> Dict[str, Any]:
        """
        补充所有外部环境数据
        
        Args:
            latitude: 纬度
            longitude: 经度
            shooting_date: 拍摄日期（YYYY-MM-DD格式）
            
        Returns:
            包含所有外部环境数据的字典
        """
        result = {}
        
        # 补充降水数据（当日 / 前30日 / 前180日 / 前365日）
        precipitation = self.get_precipitation_data(latitude, longitude, shooting_date)
        result.update(precipitation)
        
        # 补充地震烈度数据
        earthquake = self.get_earthquake_intensity(latitude, longitude)
        result.update(earthquake)
        
        # 补充坡度数据（如有DEM/坡度服务）
        slope = self.get_slope_data(latitude, longitude)
        result.update(slope)
        
        return result
    
    def get_precipitation_data(self, latitude: float, longitude: float, shooting_date: str) -> Dict[str, Any]:
        """
        获取降水数据（基于 Open-Meteo 历史降水 API）
        
        API: https://archive-api.open-meteo.com/v1/archive
        - 请求参数：latitude, longitude, start_date, end_date, daily=precipitation_sum, timezone=Asia/Shanghai
        - 返回字段：daily.precipitation_sum[]（单位：mm，逐日）
        
        本地计算：
        - 当日降水
        - 拍摄日前 30 / 180 / 365 日累计降水
        
        Args:
            latitude: 纬度
            longitude: 经度
            shooting_date: 拍摄日期（YYYY-MM-DD格式）
            
        Returns:
            降水数据字典：
            - 降水_当日_mm
            - 降水_前30日_mm
            - 降水_前180日_mm
            - 降水_前365日_mm
        """
        result: Dict[str, Optional[float]] = {
            "降水_当日_mm": None,
            "降水_前30日_mm": None,
            "降水_前180日_mm": None,
            "降水_前365日_mm": None,
        }
        
        try:
            date_obj = datetime.strptime(shooting_date, "%Y-%m-%d")
            # 最长需要前365天的数据
            start_365 = date_obj - timedelta(days=365)
            
            # 调用 Open-Meteo API，一次拿到 365 天逐日降水
            url = "https://archive-api.open-meteo.com/v1/archive"
            params = {
                "latitude": latitude,
                "longitude": longitude,
                "start_date": start_365.strftime("%Y-%m-%d"),
                "end_date": date_obj.strftime("%Y-%m-%d"),
                "daily": "precipitation_sum",
                "timezone": "Asia/Shanghai",
            }
            resp = requests.get(url, params=params, timeout=300)
            resp.raise_for_status()
            data = resp.json()
            
            daily = data.get("daily") or {}
            times = daily.get("time") or []
            precs = daily.get("precipitation_sum") or []
            if not times or not precs or len(times) != len(precs):
                print("获取降水数据失败：返回daily数据不完整")
                return result
            
            # 构建 日期 -> 降水量 的映射
            date_to_prec: Dict[str, float] = {}
            for t, p in zip(times, precs):
                try:
                    date_to_prec[str(t)] = float(p) if p is not None else 0.0
                except Exception:
                    continue
            
            today_str = shooting_date
            # 当日降水
            if today_str in date_to_prec:
                result["降水_当日_mm"] = date_to_prec[today_str]
            
            # 定义需要累积的时间窗（单位：天）
            windows = {
                "降水_前30日_mm": 30,
                "降水_前180日_mm": 180,
                "降水_前365日_mm": 365,
            }
            
            for key, days in windows.items():
                # “前N日”理解为：拍摄日前 N 天（不含当日）到拍摄日前 1 天
                start_date = date_obj - timedelta(days=days)
                end_date = date_obj - timedelta(days=1)
                
                total = 0.0
                cur = start_date
                while cur <= end_date:
                    ds = cur.strftime("%Y-%m-%d")
                    if ds in date_to_prec:
                        total += date_to_prec[ds]
                    cur += timedelta(days=1)
                result[key] = total
        
        except Exception as e:
            print(f"获取降水数据失败: {e}")
        
        return result
    
    def get_earthquake_intensity(self, latitude: float, longitude: float) -> Dict[str, Any]:
        """
        获取地震烈度数据（抗震设防参数查询）
        
        API: https://www.gb18306.net/querykz
        请求形式（GET）:
            https://www.gb18306.net/querykz
                ?x=LON
                &y=LAT
                &ak=YOUR_API_KEY
                &year=2016
                &kz=yes
        
        返回中使用：
        - ld  → 工程设计地震烈度（区划烈度）
        - epa → 设计地震动峰值加速度（可选）
        - tg  → 特征周期（可选）
        """
        result: Dict[str, Any] = {
            "地震烈度": None,
            "地震_epa": None,
            "地震_tg": None,
        }
        
        try:
            api_config = self.config.get("earthquake_api", {})
            url = api_config.get("url") or "https://www.gb18306.net/querykz"
            ak = api_config.get("api_key") or api_config.get("ak")
            if not ak:
                print("警告：未配置地震烈度API密钥(ak)")
                return result
            
            params = {
                "x": longitude,
                "y": latitude,
                "ak": ak,
                "year": api_config.get("year", 2016),
                "kz": "yes",
            }
            resp = requests.get(url, params=params, timeout=300)
            resp.raise_for_status()
            
            # 有的实现可能返回 JSON，有的可能是 text，这里统一尝试解析 JSON
            try:
                data = resp.json()
            except ValueError:
                # 如果不是标准JSON，可以根据实际返回格式再做解析
                print("地震烈度API返回不是JSON，需根据实际格式调整解析逻辑")
                return result
            
            # 按字段直接取值
            result["地震烈度"] = data.get("ld")
            result["地震_epa"] = data.get("epa")
            result["地震_tg"] = data.get("tg")
        
        except Exception as e:
            print(f"获取地震烈度数据失败: {e}")
        
        return result
    
    def get_slope_data(self, latitude: float, longitude: float) -> Dict[str, Any]:
        """
        获取坡度数据
        
        Args:
            latitude: 纬度
            longitude: 经度
            
        Returns:
            坡度数据字典
        """
        result = {
            "坡度_度": None
        }
        
        try:
            api_config = self.config.get("slope_api", {})
            if api_config.get("url"):
                # 调用坡度API
                slope = self._call_slope_api(latitude, longitude, api_config)
                result["坡度_度"] = slope
            else:
                # 如果没有配置API，返回None
                print("警告：未配置坡度API")
        
        except Exception as e:
            print(f"获取坡度数据失败: {e}")
        
        return result
    
    def _call_slope_api(self, lat: float, lon: float, api_config: Dict) -> Optional[float]:
        """
        调用坡度API（示例实现，需要根据实际API调整）
        """
        try:
            # 这里需要根据实际API文档实现
            # 示例：
            # url = api_config["url"]
            # params = {
            #     "lat": lat,
            #     "lon": lon,
            #     "api_key": api_config.get("api_key")
            # }
            # response = requests.get(url, params=params)
            # data = response.json()
            # return data.get("slope")
            
            # 暂时返回None，需要配置真实API后实现
            return None
        except Exception as e:
            print(f"调用坡度API失败: {e}")
            return None


if __name__ == "__main__":
    # 测试代码
    supplement = ExternalDataSupplement()
    result = supplement.supplement_all(29.5, 103.5, "2023-03-31")
    print(result)
