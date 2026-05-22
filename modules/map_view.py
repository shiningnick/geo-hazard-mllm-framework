import geopandas as gpd
import matplotlib.pyplot as plt
import contextily as cx
from shapely.geometry import Point
from matplotlib_scalebar.scalebar import ScaleBar
from matplotlib.patches import FancyArrowPatch
from pyproj import Transformer
import numpy as np
from typing import List, Dict, Any, Tuple
import matplotlib

# 设置中文字体，避免乱码
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题


def _convert_type_and_risk(record: Dict[str, Any]) -> Tuple[str, str]:
    """
    将系统中的灾害类型、风险等级转换为绘图用的类型和风险等级

    Returns:
        (hazard_type_en, risk_level_en)
        hazard_type_en: "Landslide" 或 "Rockfall"
        risk_level_en: "High" / "Medium" / "Low"
    """
    # 灾害类型：中文 -> 英文
    risk_type = str(record.get("风险类型", "")).strip()
    if risk_type == "滑坡":
        hazard_type = "Landslide"
    elif risk_type == "崩塌":
        hazard_type = "Rockfall"
    else:
        hazard_type = "Unknown"

    # 风险等级：FHWA 风险等级 -> 三档
    level = str(record.get("风险等级", "")).strip()
    # 这里可以根据需要调整分档规则
    if level in ("极高风险", "高风险"):
        risk_level = "High"
    elif level == "中风险":
        risk_level = "Medium"
    elif level == "低风险":
        risk_level = "Low"
    else:
        # 没有进行风险评价或未知时，视为中等
        risk_level = "Medium"

    return hazard_type, risk_level


def create_hazard_map(records: List[Dict[str, Any]]):
    """
    根据处理结果列表，在地图上绘制灾害点（嵌入 GUI 使用）。

    Args:
        records: 每条记录为 fused_record（包含 经纬度 / 风险类型 / 风险等级 等）

    Returns:
        matplotlib Figure 对象
    """
    # ===============================
    # 1. 从记录中提取点数据
    # ===============================
    data = []
    for r in records:
        if "error" in r:
            continue
        lon = r.get("经度")
        lat = r.get("纬度")
        if lon is None or lat is None:
            continue
        try:
            lon_f = float(lon)
            lat_f = float(lat)
        except (TypeError, ValueError):
            continue

        hazard_type, risk_level = _convert_type_and_risk(r)
        if hazard_type == "Unknown":
            continue
        data.append((lon_f, lat_f, hazard_type, risk_level))

    if not data:
        # 没有可绘制的数据时返回空图
        fig, ax = plt.subplots(figsize=(8, 4), dpi=150)
        ax.text(0.5, 0.5, "无有效灾害点可绘制", ha="center", va="center", fontsize=12)
        ax.axis("off")
        return fig

    colors = {"High": "red", "Medium": "yellow", "Low": "green"}
    markers = {"Rockfall": "o", "Landslide": "^"}

    # ===============================
    # 2. 构造 GeoDataFrame（WGS84）
    # ===============================
    gdf = gpd.GeoDataFrame(
        {
            "type": [d[2] for d in data],
            "risk": [d[3] for d in data],
        },
        geometry=[Point(d[0], d[1]) for d in data],
        crs="EPSG:4326",
    )

    # 投影到 Web Mercator（用于在线底图）
    gdf_wm = gdf.to_crs(epsg=3857)

    # ===============================
    # 3. 创建 2:1 画布（稍小一点，适合嵌入 GUI）
    # ===============================
    fig, ax = plt.subplots(figsize=(8, 4), dpi=150)

    # ===============================
    # 4. 手动控制显示范围（严格 2:1）
    # ===============================
    xmin, ymin, xmax, ymax = gdf_wm.total_bounds

    # 中心点
    x_center = (xmin + xmax) / 2
    y_center = (ymin + ymax) / 2

    # 数据本身的跨度
    data_width = xmax - xmin
    data_height = ymax - ymin

    # 处理边界情况：如果数据范围太小，设置最小范围
    min_range = 1000  # 最小范围（米）
    if data_width < min_range:
        data_width = min_range
        x_center = (xmin + xmax) / 2
    if data_height < min_range:
        data_height = min_range
        y_center = (ymin + ymax) / 2

    # 给一点余量
    margin = 1.3

    # 根据画布比例（2:1）反推窗口
    if data_width > 0 and data_height > 0 and data_width / data_height > 2:
        half_width = data_width * margin / 2
        half_height = half_width / 2
    else:
        half_height = data_height * margin / 2
        half_width = half_height * 2

    # 底部预留1/4空间用于图例和比例尺
    # 只显示上部3/4的数据范围，底部1/4留空
    # 将数据范围向上压缩到3/4，底部1/4不显示数据点
    data_display_ratio = 0.75  # 只显示75%的数据范围（上部）
    
    # 计算实际显示的数据高度（只显示上部3/4）
    display_height = (half_height * 2) * data_display_ratio
    display_half_height = display_height / 2
    
    # 将显示范围向上移动，使底部1/4留空
    # 中心点向上移动，使得底部1/4区域不包含数据
    y_offset = (half_height * 2) * 0.125  # 向上移动1/8，这样底部1/4留空
    adjusted_y_center = y_center + y_offset

    ax.set_xlim(x_center - half_width, x_center + half_width)
    ax.set_ylim(adjusted_y_center - display_half_height, adjusted_y_center + display_half_height)

    # ===============================
    # 5. 按 灾害类型 / 风险等级 绘制点
    # ===============================
    for t in ["Rockfall", "Landslide"]:
        for r in ["High", "Medium", "Low"]:
            subset = gdf_wm[(gdf_wm["type"] == t) & (gdf_wm["risk"] == r)]
            if not subset.empty:
                subset.plot(
                    ax=ax,
                    color=colors[r],
                    marker=markers[t],
                    markersize=15,
                    edgecolor="black",
                    linewidth=0.6,
                    label=f"{t} ({r})",
                )
    
    # ===============================
    # 5.1 添加图例
    # ===============================
    try:
        # 图例位置保持在左下角（底部1/4预留区域内）
        leg = ax.legend(
            loc="lower left",
            bbox_to_anchor=(0.02, 0.08),
            frameon=True,
            fontsize=7,
            title="图例",
            title_fontsize=8,
            ncol=2,
            borderpad=0.3,
            labelspacing=0.2,
            handlelength=0.8,
            handletextpad=0.3,
            markerscale=0.7,
        )
        # 设置图例字体（包括标题和标签）
        try:
            from matplotlib import font_manager
            # 尝试设置中文字体
            leg.get_title().set_fontfamily('SimHei')
            for text in leg.get_texts():
                text.set_fontfamily('SimHei')
        except:
            pass
        # 设置图例边框样式
        leg.get_frame().set_alpha(0.9)
        leg.get_frame().set_edgecolor('black')
        leg.get_frame().set_linewidth(0.5)
    except Exception as e:
        print(f"添加图例失败: {e}")

    # ===============================
    # 6. 底图（灰度 ASTER 地形）
    # ===============================
    try:
        cx.add_basemap(
            ax,
            source=cx.providers.NASAGIBS.ASTER_GDEM_Greyscale_Shaded_Relief,
            crs=gdf_wm.crs,
            zoom=7,
        )
    except Exception as e:
        # 如果底图获取失败，不中断绘图
        print(f"添加底图失败: {e}")

    # 缩小 NASA/GIBS 署名（尽量缩小 + 变淡）
    for txt in ax.texts:
        s = (txt.get_text() or "").lower()
        if ("nasa" in s) or ("gibs" in s) or ("imagery" in s) or ("esdis" in s) or ("gsfc" in s):
            txt.set_fontsize(4)
            txt.set_alpha(0.35)

    # ===============================
    # 7. 比例尺
    # ===============================
    try:
        ax.add_artist(
            ScaleBar(
                1,
                units="m",
                location="lower right",
                box_alpha=0,
                frameon=False,
                font_properties={"size": 6},
            )
        )
    except Exception as e:
        print(f"添加比例尺失败: {e}")

    # ===============================
    # 8. 指北针
    # ===============================
    arrow = FancyArrowPatch(
        (0.96, 0.78), (0.96, 0.92),
        transform=ax.transAxes,
        arrowstyle="simple",
        color="black",
        mutation_scale=6,
    )
    ax.add_patch(arrow)
    ax.text(
        0.96, 0.93, "N",
        transform=ax.transAxes,
        ha="center", va="bottom",
        fontsize=6, fontweight="bold",
    )

    # ===============================
    # 9. 经纬度刻度（从 Web Mercator 转回 WGS84）
    # ===============================
    try:
        transformer = Transformer.from_crs(3857, 4326, always_xy=True)

        xmin_wm, xmax_wm = ax.get_xlim()
        ymin_wm, ymax_wm = ax.get_ylim()

        xticks = np.linspace(xmin_wm, xmax_wm, 5)
        yticks = np.linspace(ymin_wm, ymax_wm, 5)

        lon_labels = []
        for x in xticks:
            lon, _ = transformer.transform(x, ymin_wm)
            lon_labels.append(f"{lon:.2f}°E")

        lat_labels = []
        for y in yticks:
            _, lat = transformer.transform(xmin_wm, y)
            lat_labels.append(f"{lat:.2f}°N")

        ax.set_xticks(xticks)
        ax.set_yticks(yticks)
        ax.set_xticklabels(lon_labels, fontsize=6, fontfamily='SimHei')
        ax.set_yticklabels(lat_labels, fontsize=6, fontfamily='SimHei')
    except Exception as e:
        print(f"设置经纬度刻度失败: {e}")

    ax.tick_params(axis="both", which="major", labelsize=6)
    ax.set_xlabel("")
    ax.set_ylabel("")

    # 调整布局，确保所有元素都在可见区域内
    fig.tight_layout(pad=1.0)
    return fig

