import streamlit as st
from streamlit_folium import st_folium
import folium
import math

# ===================== 页面全局配置 =====================
st.set_page_config(
    page_title="无人机实训考核系统",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===================== 坐标转换函数 WGS84 → GCJ-02 =====================
def wgs84_to_gcj02(lon, lat):
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

# ===================== 侧边栏 =====================
with st.sidebar:
    st.header("导航菜单")
    page_select = st.radio("功能选择", ["航线规划", "飞行监控"])
    st.divider()
    st.subheader("坐标系设置")
    coord_type = st.selectbox("坐标系", ["GCJ-02", "WGS84", "BD09"])
    st.divider()
    st.subheader("地图缩放")
    zoom = st.slider("缩放级别", 1, 18, 15)

# ===================== 主页面标题 =====================
st.title("无人机飞行实训考核系统")
st.divider()

# ===================== 左右分栏：左侧分数 + 右侧地图 =====================
col_left, col_right = st.columns([1, 2.2])

with col_left:
    st.subheader("考核成绩详情")
    st.markdown("### 总分：**77 / 100**")
    st.divider()

    # 1. 认知学习 32分
    st.markdown("**认知学习**")
    st.progress(32/100)
    st.write("得分：32")
    st.divider()

    # 2. 飞行巡检 25分
    st.markdown("**飞行巡检**")
    st.progress(25/100)
    st.write("得分：25")
    st.divider()

    # 3. 输电线路认知（满分5分）
    st.markdown("**输电线路认知（满分5分）**")
    st.progress(5/5)
    st.write("得分：5 / 5")
    st.divider()

    # 4. 故障分析（满分10分，拉满）
    st.markdown("**故障分析（满分10分）**")
    st.progress(10/10)
    st.write("得分：10 / 10")

# ===================== 右侧 高德地图（正常加载、无报错） =====================
with col_right:
    st.subheader("飞行地图")
    # 地图中心点
    lon_wgs, lat_wgs = 118.75, 32.23
    if coord_type == "GCJ-02":
        map_lon, map_lat = wgs84_to_gcj02(lon_wgs, lat_wgs)
    else:
        map_lon, map_lat = lon_wgs, lat_wgs

    # 初始化高德地图
    m = folium.Map(
        location=[map_lat, map_lon],
        zoom_start=zoom,
        tiles="https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}",
        attr="高德地图"
    )

    # 测试标记点
    point_list = [
        (118.755, 32.235),
        (118.756, 32.236)
    ]
    for plon, plat in point_list:
        if coord_type == "GCJ-02":
            plon, plat = wgs84_to_gcj02(plon, plat)
        folium.CircleMarker(
            location=[plat, plon],
            radius=7,
            color="orange",
            fill=True,
            fill_color="orange"
        ).add_to(m)

    # 渲染地图
    st_folium(m, width="100%", height=600)

# ===================== 底部备注 =====================
st.divider()
st.caption("当前页面：" + page_select + " | 坐标系：" + coord_type)
