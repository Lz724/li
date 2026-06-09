import streamlit as st
from streamlit_folium import st_folium
import folium
import math
import random

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

# ===================== 模拟输电塔杆数据（WGS84坐标） =====================
# 沿一条线路生成10个塔杆位置（经度递增）
towers_wgs = []
start_lon, start_lat = 118.73, 32.22
for i in range(10):
    lon = start_lon + i * 0.0035   # 间隔约300-400米
    lat = start_lat + 0.0005 * math.sin(i * 0.8)  # 轻微波动模拟实际走向
    towers_wgs.append((lon, lat, f"塔杆-{i+1}"))

# 定义故障点（在几个塔杆上设置故障）
fault_indices = [2, 5, 7]  # 塔杆3、6、8有故障
fault_towers = [towers_wgs[i] for i in fault_indices]

# ===================== 侧边栏 =====================
with st.sidebar:
    st.header("导航菜单")
    page_select = st.radio("功能选择", ["航线规划", "飞行监控"])
    st.divider()
    st.subheader("坐标系设置")
    coord_type = st.selectbox("坐标系", ["GCJ-02", "WGS84", "BD09"])
    st.divider()
    st.subheader("地图缩放")
    zoom = st.slider("缩放级别", 1, 18, 14)

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

# ===================== 右侧 高德地图（带真实巡检数据） =====================
with col_right:
    st.subheader(f"飞行地图 - {page_select}模式")
    
    # 地图中心点（取第三个塔杆位置）
    center_lon_wgs, center_lat_wgs = towers_wgs[4][0], towers_wgs[4][1]
    if coord_type == "GCJ-02":
        map_lon, map_lat = wgs84_to_gcj02(center_lon_wgs, center_lat_wgs)
    else:
        map_lon, map_lat = center_lon_wgs, center_lat_wgs

    # 初始化高德地图
    m = folium.Map(
        location=[map_lat, map_lon],
        zoom_start=zoom,
        tiles="https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}",
        attr="高德地图"
    )

    # ----- 1. 绘制输电线路（将所有塔杆用线连接）-----
    line_coords = []
    for lon, lat, name in towers_wgs:
        if coord_type == "GCJ-02":
            mlon, mlat = wgs84_to_gcj02(lon, lat)
        else:
            mlon, mlat = lon, lat
        line_coords.append([mlat, mlon])
    
    # 添加线路（黄色线条）
    folium.PolyLine(
        locations=line_coords,
        color="yellow",
        weight=4,
        opacity=0.8,
        popup="输电线路"
    ).add_to(m)

    # ----- 2. 绘制塔杆标记 -----
    for lon, lat, name in towers_wgs:
        if coord_type == "GCJ-02":
            mlon, mlat = wgs84_to_gcj02(lon, lat)
        else:
            mlon, mlat = lon, lat
        
        # 判断是否为故障塔杆
        is_fault = (lon, lat, name) in fault_towers
        
        # 根据模式及故障状态显示不同图标
        if page_select == "飞行监控" and is_fault:
            # 故障点：红色闪烁效果（用红色大标记）
            folium.Marker(
                location=[mlat, mlon],
                popup=f"⚠️ {name} - 绝缘子破损",
                icon=folium.Icon(color="red", icon="exclamation-triangle", prefix="fa")
            ).add_to(m)
        else:
            # 普通塔杆或航线规划模式：蓝色圆点
            folium.CircleMarker(
                location=[mlat, mlon],
                radius=6,
                color="blue" if not is_fault else "orange",
                fill=True,
                fill_color="blue" if not is_fault else "orange",
                popup=name,
                fill_opacity=0.7
            ).add_to(m)
    
    # ----- 3. 如果是飞行监控模式，添加无人机模拟位置（第5个塔杆附近）-----
    if page_select == "飞行监控":
        # 模拟无人机当前位置（在第7个塔杆附近随机偏移）
        drone_idx = 6
        drone_lon_wgs, drone_lat_wgs, _ = towers_wgs[drone_idx]
        # 添加小偏移模拟悬停
        drone_lon_wgs += random.uniform(-0.0005, 0.0005)
        drone_lat_wgs += random.uniform(-0.0003, 0.0003)
        
        if coord_type == "GCJ-02":
            drone_lon, drone_lat = wgs84_to_gcj02(drone_lon_wgs, drone_lat_wgs)
        else:
            drone_lon, drone_lat = drone_lon_wgs, drone_lat_wgs
        
        # 无人机图标（自定义）
        folium.Marker(
            location=[drone_lat, drone_lon],
            popup=f"✈️ 无人机 (正在巡检塔杆{drone_idx+1})",
            icon=folium.Icon(color="green", icon="drone", prefix="fa")
        ).add_to(m)
        
        # 添加无人机巡检路径（从起点到当前位置的虚线）
        flown_path = line_coords[:drone_idx+1]
        folium.PolyLine(
            locations=flown_path,
            color="green",
            weight=4,
            opacity=0.6,
            dash_array="5, 5",
            popup="已巡检路径"
        ).add_to(m)
    
    # 添加图例说明（通过HTML注入）
    legend_html = '''
    <div style="position: fixed; bottom: 30px; right: 30px; z-index: 1000; background-color: white; padding: 8px 12px; border-radius: 8px; border: 1px solid grey; font-size: 12px;">
        <b>图例</b><br>
        🟡 黄色线：输电线路<br>
        🔵 蓝点：普通塔杆<br>
        🔴 红点：故障塔杆(监控模式)<br>
        🟢 绿飞机：无人机(监控模式)<br>
        🟢 绿虚线：已巡检路径(监控模式)
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    # 渲染地图
    output = st_folium(m, width="100%", height=600)
    
    # 可选：显示点击交互信息
    if output and output.get("last_clicked"):
        st.success(f"点击了坐标: {output['last_clicked']}")

# ===================== 底部备注 =====================
st.divider()
st.caption(f"当前页面：{page_select} | 坐标系：{coord_type} | 塔杆数量：{len(towers_wgs)} | 故障点：{len(fault_towers)}个")
