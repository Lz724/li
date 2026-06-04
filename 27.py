import streamlit as st
import pandas as pd
import time
import math
from datetime import datetime
import folium
from streamlit_folium import folium_static
from branca.element import Figure

# ---------------------------- 坐标系转换算法 ----------------------------
def transform_lat(lng, lat):
    ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + 0.1 * lng * lat + 0.2 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * math.pi) + 40.0 * math.sin(lat / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * math.pi) + 320 * math.sin(lat * math.pi / 30.0)) * 2.0 / 3.0
    return ret

def transform_lng(lng, lat):
    ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + 0.1 * lng * lat + 0.1 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lng * math.pi) + 40.0 * math.sin(lng / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lng / 12.0 * math.pi) + 300.0 * math.sin(lng / 30.0 * math.pi)) * 2.0 / 3.0
    return ret

def wgs84_to_gcj02(lng, lat):
    if out_of_china(lng, lat):
        return lng, lat
    dlat = transform_lat(lng - 105.0, lat - 35.0)
    dlng = transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - 0.00669342162296594323 * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((6378245.0 / sqrtmagic) * math.cos(radlat) * math.pi / 180.0)
    dlng = (dlng * 180.0) / (6378245.0 / sqrtmagic * math.cos(radlat) * math.pi / 180.0)
    return lng + dlng, lat + dlat

def gcj02_to_wgs84(lng, lat):
    if out_of_china(lng, lat):
        return lng, lat
    dlng, dlat = wgs84_to_gcj02(lng, lat)
    return lng * 2 - dlng, lat * 2 - dlat

def out_of_china(lng, lat):
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)

def convert_for_display(lat, lng, src_system):
    """转换为地图显示坐标（GCJ-02，因为高德地图使用GCJ-02）"""
    if src_system == "WGS-84":
        return wgs84_to_gcj02(lng, lat)
    else:
        return lng, lat

# ---------------------------- 距离计算函数 ----------------------------
def calculate_distance(lat1, lng1, lat2, lng2):
    R = 6371000
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# ---------------------------- 初始化 Session State ----------------------------
def init_state():
    if "running" not in st.session_state:
        st.session_state.running = False
        st.session_state.seq = 0
        st.session_state.last_ts = None
        st.session_state.records = []
        st.session_state.alert_msg = ""
    
    if "coord_system" not in st.session_state:
        st.session_state.coord_system = "GCJ-02"
    
    if "point_A" not in st.session_state:
        st.session_state.point_A = {"lat": 32.2322, "lng": 118.749, "set": False}
    
    if "point_B" not in st.session_state:
        st.session_state.point_B = {"lat": 32.2343, "lng": 118.749, "set": False}
    
    if "flight_height" not in st.session_state:
        st.session_state.flight_height = 50.0
    
    if "obstacles" not in st.session_state:
        st.session_state.obstacles = [
            {"lat": 32.2328, "lng": 118.7485, "radius": 30, "name": "教学楼"},
            {"lat": 32.2335, "lng": 118.7492, "radius": 35, "name": "图书馆"},
            {"lat": 32.2330, "lng": 118.7500, "radius": 28, "name": "实验楼"},
            {"lat": 32.2325, "lng": 118.7495, "radius": 25, "name": "食堂"},
            {"lat": 32.2318, "lng": 118.7482, "radius": 22, "name": "体育馆"},
        ]
    
    if "map_zoom" not in st.session_state:
        st.session_state.map_zoom = 17

init_state()

# ---------------------------- 心跳监控辅助函数 ----------------------------
def add_heartbeat(seq, ts):
    st.session_state.records.insert(0, (seq, ts))
    if len(st.session_state.records) > 20:
        st.session_state.records.pop()
    st.session_state.seq = seq
    st.session_state.last_ts = ts

def reset_monitor():
    st.session_state.running = False
    st.session_state.seq = 0
    st.session_state.last_ts = None
    st.session_state.records = []
    st.session_state.alert_msg = ""

# ---------------------------- 高德卫星图创建函数 ----------------------------
def create_satellite_map():
    """创建使用高德卫星图的交互式地图"""
    
    # 确定地图中心点
    if st.session_state.point_A["set"]:
        disp_lng, disp_lat = convert_for_display(
            st.session_state.point_A["lat"], 
            st.session_state.point_A["lng"], 
            st.session_state.coord_system
        )
        center_lat, center_lng = disp_lat, disp_lng
    elif st.session_state.point_B["set"]:
        disp_lng, disp_lat = convert_for_display(
            st.session_state.point_B["lat"], 
            st.session_state.point_B["lng"], 
            st.session_state.coord_system
        )
        center_lat, center_lng = disp_lat, disp_lng
    else:
        center_lat, center_lng = 32.2332, 118.7492
    
    # 高德卫星图瓦片 URL
    satellite_tiles = "https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}"
    
    m = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=st.session_state.map_zoom,
        control_scale=True,
        tiles=None
    )
    
    # 添加高德卫星图
    folium.TileLayer(
        tiles=satellite_tiles,
        attr='高德地图',
        name='卫星图',
        subdomains=['1', '2', '3', '4']
    ).add_to(m)
    
    # 添加高德路网图层
    road_tiles = "https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"
    folium.TileLayer(
        tiles=road_tiles,
        attr='高德路网',
        name='路网图',
        subdomains=['1', '2', '3', '4']
    ).add_to(m)
    
    folium.LayerControl().add_to(m)
    folium.plugins.Fullscreen(position='topright').add_to(m)
    
    # 测量工具
    folium.plugins.MeasureControl(
        position='topleft',
        primary_length_unit='meters',
        secondary_length_unit='kilometers',
        primary_area_unit='sqmeters'
    ).add_to(m)
    
    # 添加 A 点
    if st.session_state.point_A["set"]:
        disp_lng, disp_lat = convert_for_display(
            st.session_state.point_A["lat"], 
            st.session_state.point_A["lng"], 
            st.session_state.coord_system
        )
        
        folium.Marker(
            location=[disp_lat, disp_lng],
            popup=f"""
            <div style="min-width: 150px;">
                <h4 style="color: green;">起点A</h4>
                <p>纬度: {st.session_state.point_A['lat']:.6f}<br>
                经度: {st.session_state.point_A['lng']:.6f}</p>
            </div>
            """,
            icon=folium.Icon(color="green", icon="play", prefix="fa"),
            tooltip="起点A"
        ).add_to(m)
        
        folium.Circle(
            radius=20,
            location=[disp_lat, disp_lng],
            color="green",
            fill=True,
            fill_opacity=0.2,
            weight=3
        ).add_to(m)
    
    # 添加 B 点
    if st.session_state.point_B["set"]:
        disp_lng, disp_lat = convert_for_display(
            st.session_state.point_B["lat"], 
            st.session_state.point_B["lng"], 
            st.session_state.coord_system
        )
        
        folium.Marker(
            location=[disp_lat, disp_lng],
            popup=f"""
            <div style="min-width: 150px;">
                <h4 style="color: red;">终点B</h4>
                <p>纬度: {st.session_state.point_B['lat']:.6f}<br>
                经度: {st.session_state.point_B['lng']:.6f}</p>
            </div>
            """,
            icon=folium.Icon(color="red", icon="flag-checkered", prefix="fa"),
            tooltip="终点B"
        ).add_to(m)
        
        folium.Circle(
            radius=20,
            location=[disp_lat, disp_lng],
            color="red",
            fill=True,
            fill_opacity=0.2,
            weight=3
        ).add_to(m)
    
    # 添加航线
    if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
        a_disp_lng, a_disp_lat = convert_for_display(
            st.session_state.point_A["lat"], 
            st.session_state.point_A["lng"], 
            st.session_state.coord_system
        )
        b_disp_lng, b_disp_lat = convert_for_display(
            st.session_state.point_B["lat"], 
            st.session_state.point_B["lng"], 
            st.session_state.coord_system
        )
        
        points = [[a_disp_lat, a_disp_lng], [b_disp_lat, b_disp_lng]]
        
        folium.PolyLine(
            points,
            color="yellow",
            weight=5,
            opacity=0.9,
            popup=f"规划航线 (高度: {st.session_state.flight_height}m)"
        ).add_to(m)
        
        # 距离标注
        distance = calculate_distance(
            st.session_state.point_A["lat"], st.session_state.point_A["lng"],
            st.session_state.point_B["lat"], st.session_state.point_B["lng"]
        )
        
        mid_lat = (a_disp_lat + b_disp_lat) / 2
        mid_lng = (a_disp_lng + b_disp_lng) / 2
        
        folium.map.Marker(
            [mid_lat, mid_lng],
            icon=folium.DivIcon(
                html=f'<div style="background-color: rgba(0,0,0,0.7); padding: 2px 8px; border-radius: 20px; color: yellow;">{distance:.0f}m</div>'
            )
        ).add_to(m)
    
    # 添加障碍物
    for obs in st.session_state.obstacles:
        obs_disp_lng, obs_disp_lat = convert_for_display(obs["lat"], obs["lng"], "WGS-84")
        
        folium.Circle(
            radius=obs["radius"],
            location=[obs_disp_lat, obs_disp_lng],
            color="red",
            fill=True,
            fill_opacity=0.4,
            weight=2,
            popup=f"{obs['name']}<br>半径: {obs['radius']}m",
            tooltip=f"{obs['name']} (半径: {obs['radius']}m)"
        ).add_to(m)
    
    # 图例
    legend_html = '''
    <div style="position: fixed; bottom: 20px; right: 20px; z-index: 1000; background-color: rgba(0,0,0,0.7); padding: 8px 12px; border-radius: 8px; color: white; font-size: 12px;">
        <p style="margin: 0;"><span style="color: #00ff00;">●</span> 起点A</p>
        <p style="margin: 0;"><span style="color: #ff0000;">●</span> 终点B</p>
        <p style="margin: 0;"><span style="color: #ffff00;">━</span> 航线</p>
        <p style="margin: 0;"><span style="color: #ff0000;">●</span> 障碍物</p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    return m

# ---------------------------- 页面配置 ----------------------------
st.set_page_config(page_title="无人机地面站系统", layout="wide")

# 侧边栏
st.sidebar.markdown("# 导航")
page = st.sidebar.radio("功能页面", ["航线规划", "飞行监控"])

st.sidebar.markdown("---")
st.sidebar.markdown("# 坐标系设置")
coord_sys = st.sidebar.selectbox(
    "输入坐标系",
    ["WGS-84", "GCJ-02(高德/百度)"],
    index=0 if st.session_state.coord_system == "WGS-84" else 1
)
st.session_state.coord_system = coord_sys.split("(")[0]

st.sidebar.markdown("---")
st.sidebar.markdown("# 地图控制")
st.session_state.map_zoom = st.sidebar.slider("缩放级别", 15, 20, st.session_state.map_zoom, 1)

st.sidebar.markdown("---")
st.sidebar.markdown("## 📖 操作说明")
st.sidebar.markdown("- 🖱️ 鼠标拖拽: 平移")
st.sidebar.markdown("- 🔍 滚轮: 缩放")
st.sidebar.markdown("- 🔲 右上角: 全屏")
st.sidebar.markdown("- 📏 左上角: 测量工具")

# ============================ 航线规划页面 ============================
if page == "航线规划":
    st.title("🗺️ 航线规划")
    st.markdown("基于高德卫星影像的无人机航线规划系统")
    
    col1, col2 = st.columns([1, 1.2])
    
    with col1:
        st.markdown("### 控制面板")
        
        st.markdown("#### 起点A")
        col_a1, col_a2 = st.columns(2)
        with col_a1:
            a_lat = st.number_input("纬度", value=st.session_state.point_A["lat"], format="%.6f", key="a_lat")
        with col_a2:
            a_lng = st.number_input("经度", value=st.session_state.point_A["lng"], format="%.6f", key="a_lng")
        if st.button("📍 设置A点", use_container_width=True):
            st.session_state.point_A = {"lat": a_lat, "lng": a_lng, "set": True}
            st.rerun()
        
        st.markdown("#### 终点B")
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            b_lat = st.number_input("纬度", value=st.session_state.point_B["lat"], format="%.6f", key="b_lat")
        with col_b2:
            b_lng = st.number_input("经度", value=st.session_state.point_B["lng"], format="%.6f", key="b_lng")
        if st.button("🎯 设置B点", use_container_width=True):
            st.session_state.point_B = {"lat": b_lat, "lng": b_lng, "set": True}
            st.rerun()
        
        st.markdown("#### 飞行参数")
        st.session_state.flight_height = st.number_input("设定飞行高度 (m)", value=st.session_state.flight_height, step=5.0)
        
        st.markdown("#### 障碍物管理")
        with st.expander("➕ 添加新障碍物", expanded=False):
            obs_name = st.text_input("名称", "新障碍物")
            col_o1, col_o2 = st.columns(2)
            with col_o1:
                obs_lat = st.number_input("纬度", value=32.2330, format="%.6f", key="obs_lat")
            with col_o2:
                obs_lng = st.number_input("经度", value=118.7495, format="%.6f", key="obs_lng")
            obs_radius = st.number_input("半径(m)", value=25, step=5)
            if st.button("✅ 添加"):
                st.session_state.obstacles.append({"lat": obs_lat, "lng": obs_lng, "radius": obs_radius, "name": obs_name})
                st.rerun()
    
    with col2:
        st.markdown("### 系统状态")
        
        if st.session_state.point_A["set"]:
            st.success(f"✅ **A点已设**\n{st.session_state.point_A['lat']:.6f}, {st.session_state.point_A['lng']:.6f}")
        else:
            st.warning("❌ **A点未设**")
        
        if st.session_state.point_B["set"]:
            st.success(f"✅ **B点已设**\n{st.session_state.point_B['lat']:.6f}, {st.session_state.point_B['lng']:.6f}")
        else:
            st.warning("❌ **B点未设**")
        
        if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
            dist = calculate_distance(a_lat, a_lng, b_lat, b_lng)
            st.success(f"📏 航线距离: {dist:.1f} 米")
        
        if st.session_state.obstacles:
            st.markdown("**🚧 障碍物列表**")
            for i, obs in enumerate(st.session_state.obstacles):
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.write(f"{i+1}. {obs['name']} ({obs['radius']}m)")
                with col_b:
                    if st.button("删除", key=f"del_{i}"):
                        st.session_state.obstacles.pop(i)
                        st.rerun()
    
    # 地图显示
    st.markdown("### 🛰️ 高德卫星地图")
    st.markdown("💡 鼠标滚轮缩放 | 鼠标拖拽平移 | 右上角全屏 | 左上角测量工具")
    
    try:
        m = create_satellite_map()
        folium_static(m, width=1100, height=550)
    except Exception as e:
        st.error(f"地图加载失败: {str(e)}")

# ============================ 飞行监控页面 ============================
else:
    st.title("🛸 无人机心跳监测系统")
    
    if st.session_state.running:
        st.markdown('<meta http-equiv="refresh" content="1">', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🚀 启动模拟", use_container_width=True):
            reset_monitor()
            st.session_state.running = True
            add_heartbeat(1, time.time())
    with col2:
        if st.button("⏸️ 暂停/恢复", use_container_width=True):
            st.session_state.running = not st.session_state.running
    with col3:
        if st.button("🛑 停止模拟", use_container_width=True):
            reset_monitor()
    
    if st.session_state.running:
        now = time.time()
        last = st.session_state.last_ts
        if last is None:
            add_heartbeat(1, now)
        else:
            diff = now - last
            if diff >= 1.0:
                for i in range(min(int(diff), 5)):
                    add_heartbeat(st.session_state.seq + 1, last + i + 1)
        
        if st.session_state.last_ts and (time.time() - st.session_state.last_ts) > 3.0:
            st.error(f"⚠️ 超时！已 {time.time() - st.session_state.last_ts:.1f} 秒无心跳")
        else:
            st.success("✅ 连接正常")
    
    st.metric("最新心跳序号", st.session_state.seq if st.session_state.seq > 0 else "—")
    
    if st.session_state.records:
        df = pd.DataFrame(st.session_state.records, columns=["序号", "时间戳"])
        df["时间"] = pd.to_datetime(df["时间戳"], unit="s")
        st.line_chart(df.set_index("时间")["序号"])
        
        df["接收时间"] = df["时间戳"].apply(lambda x: datetime.fromtimestamp(x).strftime("%H:%M:%S"))
        st.dataframe(df[["序号", "接收时间"]], use_container_width=True)

st.markdown("---")
st.markdown("© 无人机地面站 | 高德卫星图 | WGS-84/GCJ-02 坐标转换")
