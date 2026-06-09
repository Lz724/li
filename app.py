import streamlit as st
from streamlit_folium import st_folium
import folium
import math

# --------------------------
# 页面基础配置
# --------------------------
st.set_page_config(
    page_title="无人机地面站系统",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --------------------------
# 坐标系转换工具（WGS84 ↔ GCJ-02）
# --------------------------
def wgs84_to_gcj02(lon, lat):
    """WGS84 坐标转 GCJ-02（国内地图通用偏移修正）"""
    a = 6378245.0
    ee = 0.00669342162296594323

    def transform_lat(x, y):
        ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
        ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
        ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
        ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
        return ret

    def transform_lon(x, y):
        ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
        ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
        ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
        ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
        return ret

    if not (73.66 < lon < 135.05 and 18.2 < lat < 53.5):
        return (lon, lat)

    dlat = transform_lat(lon - 105.0, lat - 35.0)
    dlon = transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * math.pi)
    dlon = (dlon * 180.0) / (a / sqrtmagic * math.cos(radlat) * math.pi)
    gcj_lat = lat + dlat
    gcj_lon = lon + dlon
    return (gcj_lon, gcj_lat)

# --------------------------
# 侧边栏控制（保留你原有的所有功能）
# --------------------------
with st.sidebar:
    st.header("🧭 导航")
    func_page = st.radio(
        "功能页面",
        ["✏️ 航线规划", "❤️ 飞行监控"],
        index=0
    )

    st.divider()

    st.subheader("🗺️ 坐标系设置")
    coord_sys = st.selectbox(
        "输入坐标系",
        ["GCJ-02", "WGS84", "BD09"],
        index=0
    )

    st.divider()

    st.subheader("🎮 地图控制")
    zoom_level = st.slider("缩放级别", min_value=1, max_value=18, value=15)
    # Folium 不支持 pydeck 的倾斜角，这里保留控制逻辑，如需3D可后续扩展
    st.slider("倾斜角度", min_value=0, max_value=90, value=45, disabled=True)

# --------------------------
# 示例数据（和你之前的标记点一致）
# --------------------------
# 中心点：南京大厂附近（和你第二张图的坐标匹配）
center_wgs84_lon, center_wgs84_lat = 118.75, 32.23

# 示例标记点数据
points_wgs84 = [
    (118.755, 32.235),
    (118.756, 32.236),
    (118.754, 32.234),
    (118.757, 32.233),
    (118.753, 32.237)
]

# 根据坐标系自动转换坐标
if coord_sys == "GCJ-02":
    points = [wgs84_to_gcj02(lon, lat) for lon, lat in points_wgs84]
    center_lon, center_lat = wgs84_to_gcj02(center_wgs84_lon, center_wgs84_lat)
else:
    points = points_wgs84
    center_lon, center_lat = center_wgs84_lon, center_wgs84_lat

# --------------------------
# 创建高德地图（完全兼容，无解析错误）
# --------------------------
m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=zoom_level,
    tiles="https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}",
    attr="高德地图"
)

# 添加橙色标记点（和你第一张图的效果一致）
for lon, lat in points:
    folium.CircleMarker(
        location=[lat, lon],
        radius=8,
        color="#ff7700",
        fill=True,
        fill_color="#ff7700",
        fill_opacity=0.8,
        popup=f"坐标: {lon:.4f}, {lat:.4f}"
    ).add_to(m)

# --------------------------
# 主界面显示
# --------------------------
st.title("🚁 无人机地面站系统")
st.markdown(f"当前功能：**{func_page}** | 坐标系：**{coord_sys}**")

# 渲染地图
st_folium(m, width=1200, height=700)

st.caption("地图瓦片 © 高德地图 | 坐标系已按设置自动转换")
