# -*- coding: utf-8 -*-
"""
模块3.2：照片基础信息提取模块（客观信息）
功能定位：从照片自身元数据中提取客观、不可主观判断的信息
基于现有的 读取文件属性.py 代码
"""
import os
from typing import Dict, Any, Optional
from datetime import datetime
import exifread
from PIL import Image
import win32com.client


def _parse_ratio_any(x: Any) -> Optional[float]:
    """
    把 exifread 可能出现的数值表示统一转成 float
    """
    try:
        if x is None:
            return None
        s = str(x).strip()
        if s == "":
            return None
        if "/" in s:
            a, b = s.split("/", 1)
            a, b = float(a), float(b)
            if b == 0:
                return None
            return a / b
        return float(s)
    except Exception:
        return None


def _parse_gps_list_to_deg(gps_val: Any, ref: Any) -> Optional[float]:
    """
    把 exifread 输出的 GPS 格式转成十进制度
    """
    try:
        if gps_val is None or ref is None:
            return None

        s = str(gps_val).strip().replace("[", "").replace("]", "")
        parts = [p.strip() for p in s.split(",") if p.strip()]
        if len(parts) < 3:
            return None

        deg = _parse_ratio_any(parts[0])
        minute = _parse_ratio_any(parts[1])
        sec = _parse_ratio_any(parts[2])
        if deg is None or minute is None or sec is None:
            return None

        val = deg + minute / 60.0 + sec / 3600.0
        r = str(ref).strip().upper()
        if r in ("S", "W"):
            val = -val
        return val
    except Exception:
        return None


def _parse_exif_datetime_to_datetime(dt_str: Any) -> Optional[datetime]:
    """
    把 EXIF DateTimeOriginal: "2023:03:31 11:04:43"
    转为 datetime 对象
    """
    try:
        if dt_str is None:
            return None
        s = str(dt_str).strip()
        if s == "":
            return None
        # 常见格式：YYYY:MM:DD HH:MM:SS
        return datetime.strptime(s, "%Y:%m:%d %H:%M:%S")
    except Exception:
        return None


class MetadataExtractor:
    """照片基础信息提取器"""
    
    def __init__(self):
        pass
    
    def extract_all(self, image_path: str) -> Dict[str, Any]:
        """
        提取图片的所有基础信息
        
        Args:
            image_path: 图片路径
            
        Returns:
            包含所有提取信息的字典
        """
        result = {
            "image_path": image_path,
            "extraction_time": datetime.now().isoformat()
        }
        
        # 提取EXIF信息
        exif_data = self._extract_exif(image_path)
        result.update(exif_data)
        
        # 提取GPS信息（经纬度、高程）
        gps_data = self._extract_gps(exif_data)
        result.update(gps_data)
        
        # 提取拍摄时间
        shooting_time = self._extract_shooting_time(exif_data)
        result["拍摄时间"] = shooting_time
        result["拍摄日期"] = shooting_time.strftime("%Y-%m-%d") if shooting_time else None
        
        # 提取图片基本信息
        image_info = self._extract_image_info(image_path)
        result.update(image_info)
        
        return result
    
    def _extract_exif(self, image_path: str) -> Dict[str, Any]:
        """提取EXIF信息"""
        exif_dict = {}
        try:
            with open(image_path, "rb") as f:
                tags = exifread.process_file(f, details=True)
            for k, v in tags.items():
                exif_dict[k] = str(v)
        except Exception as e:
            exif_dict["exif_error"] = str(e)
        return exif_dict
    
    def _extract_gps(self, exif_dict: Dict[str, Any]) -> Dict[str, Any]:
        """提取GPS信息（经纬度、高程）"""
        # 从EXIF中获取GPS相关字段
        lat_raw = exif_dict.get("GPS GPSLatitude")
        lat_ref = exif_dict.get("GPS GPSLatitudeRef")
        lon_raw = exif_dict.get("GPS GPSLongitude")
        lon_ref = exif_dict.get("GPS GPSLongitudeRef")
        alt_raw = exif_dict.get("GPS GPSAltitude")
        
        # 转换为十进制度
        latitude = _parse_gps_list_to_deg(lat_raw, lat_ref)
        longitude = _parse_gps_list_to_deg(lon_raw, lon_ref)
        altitude = _parse_ratio_any(alt_raw)
        
        return {
            "纬度": round(latitude, 6) if latitude is not None else None,
            "经度": round(longitude, 6) if longitude is not None else None,
            "高程_m": round(altitude, 2) if altitude is not None else None,
        }
    
    def _extract_shooting_time(self, exif_dict: Dict[str, Any]) -> Optional[datetime]:
        """提取拍摄时间"""
        # 尝试多个可能的字段
        time_fields = [
            "EXIF DateTimeOriginal",
            "Image DateTime",
            "EXIF DateTimeDigitized"
        ]
        
        for field in time_fields:
            dt_str = exif_dict.get(field)
            if dt_str:
                dt = _parse_exif_datetime_to_datetime(dt_str)
                if dt:
                    return dt
        
        return None
    
    def _extract_image_info(self, image_path: str) -> Dict[str, Any]:
        """提取图片基本信息（尺寸等）"""
        info = {}
        try:
            with Image.open(image_path) as im:
                info["图片宽度_px"] = im.width
                info["图片高度_px"] = im.height
                info["图片模式"] = im.mode
                dpi = im.info.get("dpi")
                if dpi:
                    info["DPI_X"] = dpi[0]
                    info["DPI_Y"] = dpi[1]
        except Exception as e:
            info["image_error"] = str(e)
        
        return info
    
    def extract_standard_fields(self, image_path: str) -> Dict[str, Any]:
        """
        提取标准化的基础信息字段（用于后续模块）
        
        Args:
            image_path: 图片路径
            
        Returns:
            标准化字段字典：
            - 编号: 图片编号
            - 纬度: 纬度（保留6位小数）
            - 经度: 经度（保留6位小数）
            - 高程_m: 高程（米，保留2位小数）
            - 拍摄日期: 拍摄日期（YYYY-MM-DD格式）
            - 拍摄时间: 拍摄时间（datetime对象）
        """
        all_data = self.extract_all(image_path)
        
        # 生成编号（基于文件名，不含扩展名）
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        
        return {
            "编号": base_name,
            "纬度": all_data.get("纬度"),
            "经度": all_data.get("经度"),
            "高程_m": all_data.get("高程_m"),
            "拍摄日期": all_data.get("拍摄日期"),
            "拍摄时间": all_data.get("拍摄时间")
        }


if __name__ == "__main__":
    # 测试代码
    extractor = MetadataExtractor()
    test_image = r"C:\Users\UCD-K\Desktop\科研工作\文章撰写-AI赋能地质调查\地质调查一张图\图片测试\A1.jpg"
    result = extractor.extract_standard_fields(test_image)
    print(result)
