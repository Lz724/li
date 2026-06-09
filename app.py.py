import streamlit as st
import pydeck as pdk
import math

# --------------------------
# 页面配置
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
# 侧边栏控制
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

    st.subheader("🎮 3D地图控制")
    zoom_level = st.slider("缩放级别", min_value=1, max_value=18, value=15)
    tilt_angle = st.slider("倾斜角度", min_value=0, max_value=90, value=45)

# --------------------------
# 地图瓦片配置（高德地图，GCJ-02，国内稳定访问）
# --------------------------
AMAP_TILE_URL = "https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"

# --------------------------
# 示例标记点（对应你第一张图的橙色点）
# --------------------------
# 示例中心点：南京大厂附近（和你第二张图的坐标匹配）
center_wgs84_lon, center_wgs84_lat = 118.75, 32.23

# 示例标记点数据
points_wgs84 = [
    (118.755, 32.235),
    (118.756, 32.236),
    (118.754, 32.234),
    (118.757, 32.233),
    (118.753, 32.237)
]

# 根据坐标系转换坐标
if coord_sys == "GCJ-02":
    points = [wgs84_to_gcj02(lon, lat) for lon, lat in points_wgs84]
    center_lon, center_lat = wgs84_to_gcj02(center_wgs84_lon, center_wgs84_lat)
else:
    points = points_wgs84
    center_lon, center_lat = center_wgs84_lon, center_wgs84_lat

# 转为 pydeck 可用格式
point_data = [{
    "lon": lon,
    "lat": lat,
    "color": [255, 119, 0, 200]  # 橙色标记点，和你第一张图一致
} for lon, lat in points]

# --------------------------
# 构建地图图层
# --------------------------
# 标记点图层
point_layer = pdk.Layer(
    "ScatterplotLayer",
    data=point_data,
    get_position=["lon", "lat"],
    get_radius=50,
    get_fill_color="color",
    pickable=True,
    auto_highlight=True
)

# 高德地图瓦片图层
tile_layer = pdk.Layer(
    "TileLayer",
    data="",
    get_tile_url=AMAP_TILE_URL,
    tile_size=256,
    s="abc"
)

# 地图视图
view_state = pdk.ViewState(
    longitude=center_lon,
    latitude=center_lat,
    zoom=zoom_level,
    pitch=tilt_angle,
    bearing=0
)

# 渲染地图（禁用默认黑色底图）
deck = pdk.Deck(
    layers=[tile_layer, point_layer],
    initial_view_state=view_state,
    map_style=None,
    tooltip={"text": "坐标: {lon}, {lat}"}
)

# --------------------------
# 主界面显示
# --------------------------
st.title("🚁 无人机地面站系统")
st.markdown(f"当前功能：**{func_page}** | 坐标系：**{coord_sys}**")

st.pydeck_chart(deck, use_container_width=True)

st.caption("地图瓦片 © 高德地图 | 坐标系已按设置自动转换")
