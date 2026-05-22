# -*- coding: utf-8 -*-
"""
模块3.1：图片输入与管理模块
功能定位：负责野外调查照片的接收、编号与统一管理
"""
import os
from typing import List, Dict, Any
from pathlib import Path


class ImageInputManager:
    """图片输入与管理类"""
    
    def __init__(self, input_dir: str = None):
        """
        初始化图片管理器
        
        Args:
            input_dir: 图片输入目录，如果为None则使用默认目录
        """
        if input_dir is None:
            from config import INPUT_DIR
            input_dir = INPUT_DIR
        self.input_dir = input_dir
        os.makedirs(input_dir, exist_ok=True)
    
    def add_image(self, image_path: str) -> Dict[str, Any]:
        """
        添加单张图片
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            包含图片信息的字典，包括：
            - id: 图片编号（基于文件名）
            - path: 图片完整路径
            - name: 文件名
            - exists: 文件是否存在
        """
        if not os.path.exists(image_path):
            return {
                "id": os.path.basename(image_path),
                "path": image_path,
                "name": os.path.basename(image_path),
                "exists": False,
                "error": "文件不存在"
            }
        
        # 生成图片编号（使用文件名，不含扩展名）
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        
        return {
            "id": base_name,
            "path": os.path.abspath(image_path),
            "name": os.path.basename(image_path),
            "exists": True
        }
    
    def add_images_batch(self, image_paths: List[str]) -> List[Dict[str, Any]]:
        """
        批量添加图片
        
        Args:
            image_paths: 图片文件路径列表
            
        Returns:
            图片信息字典列表
        """
        results = []
        for path in image_paths:
            result = self.add_image(path)
            results.append(result)
        return results
    
    def scan_directory(self, directory: str = None, extensions: List[str] = None) -> List[Dict[str, Any]]:
        """
        扫描目录中的图片文件
        
        Args:
            directory: 要扫描的目录，如果为None则使用input_dir
            extensions: 支持的图片扩展名列表，默认['.jpg', '.jpeg', '.png', '.bmp']
            
        Returns:
            图片信息字典列表
        """
        if directory is None:
            directory = self.input_dir
        
        if extensions is None:
            extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff']
        
        image_paths = []
        for ext in extensions:
            image_paths.extend(Path(directory).glob(f"*{ext}"))
            image_paths.extend(Path(directory).glob(f"*{ext.upper()}"))
        
        return self.add_images_batch([str(p) for p in image_paths])
    
    def validate_image(self, image_info: Dict[str, Any]) -> bool:
        """
        验证图片信息是否有效
        
        Args:
            image_info: 图片信息字典
            
        Returns:
            是否有效
        """
        return image_info.get("exists", False) and os.path.exists(image_info.get("path", ""))


if __name__ == "__main__":
    # 测试代码
    manager = ImageInputManager()
    test_image = r"C:\Users\UCD-K\Desktop\科研工作\文章撰写-AI赋能地质调查\地质调查一张图\图片测试\A1.jpg"
    result = manager.add_image(test_image)
    print(result)
