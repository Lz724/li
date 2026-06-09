import streamlit as st
import pydeck as pdk
import math

# --------------------------
# 1. 配置页面基础信息
# --------------------------
st.set_page_config(page_title="无人机地面站系统", layout="wide")

# --------------------------
# 2. 坐标系转换工具（WGS84 ↔ GCJ-02）
# --------------------------
# 说明：国内地图（高德/腾讯/GCJ-02）有偏移，需要转换才能和标记点对齐
def wgs84_to_gcj02(lon, lat):
    """WGS84 转 GCJ-02（国内地图通用偏移）"""
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
# 3. 侧边栏控制（和你第一张图保持一致）
# --------------------------
with st.sidebar:
    st.header("导航")
    func_page = st.radio("功能页面", ["航线规划", "飞行监控"], index=0)

    st.divider()

    st.subheader("坐标系设置")
    coord_sys = st.selectbox("输入坐标系", ["GCJ-02", "WGS84", "BD09"], index=0)

    st.divider()

    st.subheader("3D地图控制")
    zoom_level = st.slider("缩放级别", min_value=1, max_value=18, value=15)
    tilt_angle = st.slider("倾斜角度", min_value=0, max_value=90, value=45)

# --------------------------
# 4. 配置高德地图瓦片（和第二张图风格一致）
# --------------------------
# 高德地图标准彩色瓦片源（GCJ-02坐标系，国内可稳定访问）
AMAP_TILE_URL = "https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"

# --------------------------
# 5. 示例标记点（对应你第一张图的橙色点）
# --------------------------
# 这里用你第二张图的起点A作为示例中心点
points_wgs84 = [
    (118.755, 32.235),
    (118.756, 32.236),
    (118.754, 32.234),
    (118.757, 32.233),
    (118.753, 32.237)
]

# 根据坐标系转换点坐标
if coord_sys == "GCJ-02":
    points = [wgs84_to_gcj02(lon, lat) for lon, lat in points_wgs84]
else:
    points = points_wgs84

# 转为 pydeck 需要的格式
point_data = [{
    "lon": lon,
    "lat": lat,
    "color": [255, 119, 0, 200]  # 橙色，和你第一张图一致
} for lon, lat in points]

# --------------------------
# 6. 创建 pydeck 地图
# --------------------------
# 中心点坐标（和第二张图的起点A对齐）
center_lon, center_lat = wgs84_to_gcj02(118.75, 32.23)

# 标记点图层
point_layer = pdk.Layer(
    "ScatterplotLayer",
    data=point_data,
    get_position=["lon", "lat"],
    get_radius=50,  # 点的大小，可根据缩放级别调整
    get_fill_color="color",
    pickable=True,
    auto_highlight=True
)

# 自定义高德瓦片图层
tile_layer = pdk.Layer(
    "TileLayer",
    data="",
    get_tile_url=AMAP_TILE_URL,
    tile_size=256,
    s="abc"  # 高德瓦片的子域名（a/b/c）
)

# 地图视图配置
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
    map_style=None,  # 关键：关闭CARTO默认黑色底图
    tooltip={"text": "坐标: {lon}, {lat}"}
)

# 在 Streamlit 中显示地图
st.pydeck_chart(deck, use_container_width=True)

st.caption("地图瓦片 © 高德地图 | 坐标系: " + coord_sys)
