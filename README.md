# geo-hazard-mllm-framework

**An AI-Enabled Geological Hazard Investigation Framework** — core code for image-based hazard identification and FHWA risk assessment (companion to *Geophysical Research Letters* submission).

基于多模态大模型的野外地质灾害照片自动识别与 FHWA 风险评价系统。

## 功能概览

| 模块 | 文件 | 说明 |
|------|------|------|
| 图形界面 | `gui.py` | 选图、批量处理、风险评价、空间分布图 |
| 命令行 | `main.py` | 单张/目录批处理、模型对比 |
| 读图与元数据 | `modules/metadata_extraction.py` | EXIF / 照片属性提取经纬度、高程、时间 |
| 指标提取 | `modules/ai_extraction.py` + `indicator_standards.py` | 两阶段：风险类型识别 → 规范化指标提取 |
| 环境数据 | `modules/external_data.py` | Open-Meteo 降水等（可选） |
| 数据融合 | `modules/data_fusion.py` | 多源融合并输出 Excel |
| 风险评估 | `modules/risk_assessment.py` | FHWA 滑坡/崩塌危险性评价 |
| 流程调度 | `modules/system_scheduler.py` | 串联上述模块 |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 演示模式（无需 API，推荐审稿人先试）

```bash
# Windows PowerShell
$env:DEMO_MODE = "1"
python demo_run.py
```

将处理 `demo_data/images/` 下 4 张样例照片，使用 `demo_data/sample_results.json` 中的预置指标与风险结果，输出至 `output/`。

### 3. 图形界面

```bash
# 演示模式
$env:DEMO_MODE = "1"
python gui.py
```

点击 **「加载演示数据」** → 勾选 **「进行风险评价」** → **「开始处理」**。

### 4. 正式运行（需配置大模型 API）

```powershell
$env:OPENAI_API_KEY = "your-key"
$env:OPENAI_BASE_URL = "https://api.openai.com/v1"   # 或兼容网关
$env:DEFAULT_MODEL_NAME = "gpt-4o-mini"
python main.py -i demo_data/images/demo_01_landslide.jpg --risk
```

## 演示数据

`demo_data/images/` 包含 4 张野外调查照片（西藏林芝一带，含 EXIF 定位信息）：

| 文件 | 说明 |
|------|------|
| `demo_01_landslide.jpg` | 滑坡样例 1 |
| `demo_02_landslide.jpg` | 滑坡样例 2 |
| `demo_03_rockfall.jpg` | 崩塌样例 |
| `demo_04_landslide.jpg` | 滑坡样例 3 |

预置识别与评价结果见 `demo_data/sample_results.json`。

## 项目结构

```
geohazard-risk-identification/
├── gui.py                 # GUI 入口
├── main.py                # CLI 入口
├── demo_run.py            # 演示脚本（DEMO_MODE=1）
├── config.py              # 配置（从环境变量读 API Key）
├── config.example.py
├── requirements.txt
├── modules/
│   ├── system_scheduler.py    # 流程调度
│   ├── image_input.py
│   ├── metadata_extraction.py # 读图/元数据
│   ├── ai_extraction.py       # 大模型指标提取
│   ├── indicator_standards.py # 指标标准体系
│   ├── risk_assessment.py     # FHWA 风险评价
│   ├── data_fusion.py
│   ├── external_data.py
│   ├── map_view.py            # 风险空间分布图
│   └── demo_mode.py           # 演示模式
├── demo_data/
│   ├── images/            # 4 张演示照片
│   └── sample_results.json
├── input/                 # 默认输入目录
└── output/                # 结果输出（Excel、地图）
```

## 处理流程

```
照片输入 → EXIF/属性提取(经纬度等)
        → AI 两阶段指标提取(滑坡/崩塌 + 规范指标)
        → 外部环境数据(可选)
        → 指标融合 → Excel
        → FHWA 风险评价(可选) → 风险等级/指数
        → 空间分布图(可选)
```

## 配置说明

- **切勿**将 API Key 提交到公开仓库；使用环境变量或本地 `.env`（已加入 `.gitignore`）。
- `DEMO_MODE=1` 时跳过所有大模型与外部 API 调用。
- Windows 下 `metadata_extraction.py` 可通过照片属性补充 GPS；Linux 主要依赖 EXIF。

## 引用

如在论文中使用本代码，请注明对应研究及仓库地址。

## 许可证

仅供学术研究使用。
