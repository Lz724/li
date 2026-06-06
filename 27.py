"""
无人机地面站系统 - 高德地图版本
使用 folium + 高德卫星图，在 Streamlit Cloud 上可正常显示
"""

import streamlit as st
import pandas as pd
import time
import math
from datetime import datetime
import folium
from streamlit_folium import folium_static

# ============================ 坐标系转换算法 ============================

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
    """转换为地图显示坐标（高德使用 GCJ-02）"""
    if src_system == "WGS-84":
        return wgs84_to_gcj02(lng, lat)
    else:
        return lng, lat

# ============================ 距离计算 ============================

def calculate_distance(lat1, lng1, lat2, lng2):
    R = 6371000
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# ============================ 初始化 Session State ============================

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
        st.session_state.map_zoom = 16

init_state()

# ============================ 心跳监控函数 ============================

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

# ============================ 创建高德地图 ============================

def create_amap():
    """创建高德卫星地图"""
    
    # 确定地图中心
    if st.session_state.point_A["set"]:
        lng, lat = convert_for_display(
            st.session_state.point_A["lat"], 
            st.session_state.point_A["lng"], 
            st.session_state.coord_system
        )
        center_lat, center_lng = lat, lng
    elif st.session_state.point_B["set"]:
        lng, lat = convert_for_display(
            st.session_state.point_B["lat"], 
            st.session_state.point_B["lng"], 
            st.session_state.coord_system
        )
        center_lat, center_lng = lat, lng
    else:
        center_lat, center_lng = 32.2332, 118.7492
    
    # 高德卫星图瓦片
    satellite_tiles = "https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}"
    
    m = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=st.session_state.map_zoom,
        control_scale=True,
        tiles=None
    )
    
    # 添加卫星图
    folium.TileLayer(
        tiles=satellite_tiles,
        attr='高德地图',
        name='卫星图',
        subdomains=['1', '2', '3', '4']
    ).add_to(m)
    
    # 添加路网图
    road_tiles = "https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"
    folium.TileLayer(
        tiles=road_tiles,
        attr='高德路网',
        name='路网图',
        subdomains=['1', '2', '3', '4']
    ).add_to(m)
    
    folium.LayerControl().add_to(m)
    folium.plugins.Fullscreen(position='topright').add_to(m)
    
    # 添加 A 点
    if st.session_state.point_A["set"]:
        lng, lat = convert_for_display(
            st.session_state.point_A["lat"], 
            st.session_state.point_A["lng"], 
            st.session_state.coord_system
        )
        folium.Marker(
            location=[lat, lng],
            popup=f"起点A<br>纬度: {st.session_state.point_A['lat']:.6f}<br>经度: {st.session_state.point_A['lng']:.6f}",
            icon=folium.Icon(color="green", icon="play", prefix="fa"),
            tooltip="起点A"
        ).add_to(m)
        folium.Circle([lat, lng], radius=20, color="green", fill=True, fill_opacity=0.2).add_to(m)
    
    # 添加 B 点
    if st.session_state.point_B["set"]:
        lng, lat = convert_for_display(
            st.session_state.point_B["lat"], 
            st.session_state.point_B["lng"], 
            st.session_state.coord_system
        )
        folium.Marker(
            location=[lat, lng],
            popup=f"终点B<br>纬度: {st.session_state.point_B['lat']:.6f}<br>经度: {st.session_state.point_B['lng']:.6f}",
            icon=folium.Icon(color="red", icon="flag-checkered", prefix="fa"),
            tooltip="终点B"
        ).add_to(m)
        folium.Circle([lat, lng], radius=20, color="red", fill=True, fill_opacity=0.2).add_to(m)
    
    # 添加航线
    if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
        a_lng, a_lat = convert_for_display(
            st.session_state.point_A["lat"], 
            st.session_state.point_A["lng"], 
            st.session_state.coord_system
        )
        b_lng, b_lat = convert_for_display(
            st.session_state.point_B["lat"], 
            st.session_state.point_B["lng"], 
            st.session_state.coord_system
        )
        points = [[a_lat, a_lng], [b_lat, b_lng]]
        folium.PolyLine(points, color="yellow", weight=5, opacity=0.9, 
                       popup=f"航线 | 高度: {st.session_state.flight_height}m").add_to(m)
        
        # 距离标注
        distance = calculate_distance(
            st.session_state.point_A["lat"], st.session_state.point_A["lng"],
            st.session_state.point_B["lat"], st.session_state.point_B["lng"]
        )
        mid_lat = (a_lat + b_lat) / 2
        mid_lng = (a_lng + b_lng) / 2
        folium.map.Marker(
            [mid_lat, mid_lng],
            icon=folium.DivIcon(
                html=f'<div style="background:rgba(0,0,0,0.7);padding:2px 8px;border-radius:20px;color:yellow;">{distance:.0f}m</div>'
            )
        ).add_to(m)
    
    # 添加障碍物
    for obs in st.session_state.obstacles:
        lng, lat = convert_for_display(obs["lat"], obs["lng"], "WGS-84")
        folium.Circle(
            radius=obs["radius"],
            location=[lat, lng],
            color="red",
            fill=True,
            fill_opacity=0.4,
            popup=f"{obs['name']}<br>半径: {obs['radius']}m",
            tooltip=obs['name']
        ).add_to(m)
    
    # 图例
    legend_html = '''
    <div style="position: fixed; bottom: 20px; right: 20px; z-index: 1000; background: rgba(0,0,0,0.7); padding: 8px 12px; border-radius: 8px; color: white; font-size: 12px;">
        <p style="margin:0;"><span style="color:#00ff00;">●</span> 起点A</p>
        <p style="margin:0;"><span style="color:#ff0000;">●</span> 终点B</p>
        <p style="margin:0;"><span style="color:#ffff00;">━</span> 航线</p>
        <p style="margin:0;"><span style="color:#ff0000;">●</span> 障碍物</p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    return m

# ============================ 页面配置 ============================

st.set_page_config(page_title="无人机地面站系统", layout="wide")

# ============================ 侧边栏 ============================

st.sidebar.markdown("# 🚁 导航")
page = st.sidebar.radio("功能页面", ["🗺️ 航线规划", "💓 飞行监控"])

st.sidebar.markdown("---")
st.sidebar.markdown("# 📐 坐标系设置")

coord_sys = st.sidebar.selectbox(
    "输入坐标系", ["WGS-84", "GCJ-02(高德/百度)"],
    index=0 if st.session_state.coord_system == "WGS-84" else 1
)
st.session_state.coord_system = coord_sys.split("(")[0]

st.sidebar.markdown("---")
st.sidebar.markdown("# 🗺️ 地图控制")
st.session_state.map_zoom = st.sidebar.slider("缩放级别", 14, 19, st.session_state.map_zoom, 1)

st.sidebar.markdown("---")
st.sidebar.markdown("## 📖 操作说明")
st.sidebar.markdown("- 🖱️ 鼠标拖拽: 平移地图")
st.sidebar.markdown("- 🔍 滚轮: 缩放地图")
st.sidebar.markdown("- 🔲 右上角: 全屏显示")
st.sidebar.markdown("- 🟢 绿色: 起点A")
st.sidebar.markdown("- 🔴 红色: 终点B/障碍物")
st.sidebar.markdown("- 🟡 黄色: 规划航线")

# ============================ 航线规划页面 ============================

if page == "🗺️ 航线规划":
    st.title("🗺️ 航线规划")
    st.markdown("基于高德卫星图的无人机航线规划系统 | 支持 WGS-84 / GCJ-02 坐标系转换")
    
    col1, col2 = st.columns([1, 1.2])
    
    with col1:
        st.markdown("### 🎮 控制面板")
        
        # 起点A
        st.markdown("#### 📍 起点A")
        a_lat = st.number_input("纬度", value=st.session_state.point_A["lat"], format="%.6f", key="a_lat")
        a_lng = st.number_input("经度", value=st.session_state.point_A["lng"], format="%.6f", key="a_lng")
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("📍 设置A点", use_container_width=True):
                st.session_state.point_A = {"lat": a_lat, "lng": a_lng, "set": True}
                st.rerun()
        with col_btn2:
            if st.button("🗑️ 清除A点", use_container_width=True):
                st.session_state.point_A["set"] = False
                st.rerun()
        
        # 终点B
        st.markdown("#### 🎯 终点B")
        b_lat = st.number_input("纬度", value=st.session_state.point_B["lat"], format="%.6f", key="b_lat")
        b_lng = st.number_input("经度", value=st.session_state.point_B["lng"], format="%.6f", key="b_lng")
        col_btn3, col_btn4 = st.columns(2)
        with col_btn3:
            if st.button("🎯 设置B点", use_container_width=True):
                st.session_state.point_B = {"lat": b_lat, "lng": b_lng, "set": True}
                st.rerun()
        with col_btn4:
            if st.button("🗑️ 清除B点", use_container_width=True):
                st.session_state.point_B["set"] = False
                st.rerun()
        
        # 飞行参数
        st.markdown("#### ✈️ 飞行参数")
        st.session_state.flight_height = st.number_input("飞行高度 (m)", value=st.session_state.flight_height, step=5.0)
        
        # 障碍物管理
        st.markdown("#### 🚧 障碍物管理")
        with st.expander("➕ 添加新障碍物", expanded=False):
            obs_name = st.text_input("名称", "新障碍物")
            col_o1, col_o2 = st.columns(2)
            with col_o1:
                obs_lat = st.number_input("纬度", value=32.2330, format="%.6f", key="obs_lat")
            with col_o2:
                obs_lng = st.number_input("经度", value=118.7495, format="%.6f", key="obs_lng")
            obs_radius = st.number_input("半径(m)", value=25, step=5, key="obs_radius")
            if st.button("✅ 确认添加", key="add_obs"):
                st.session_state.obstacles.append({"lat": obs_lat, "lng": obs_lng, "radius": obs_radius, "name": obs_name})
                st.rerun()
    
    with col2:
        st.markdown("### 📊 系统状态")
        
        if st.session_state.point_A["set"]:
            st.success(f"✅ **A点已设**\n\n📍 {st.session_state.point_A['lat']:.6f}, {st.session_state.point_A['lng']:.6f}")
        else:
            st.warning("❌ **A点未设**")
        
        if st.session_state.point_B["set"]:
            st.success(f"✅ **B点已设**\n\n📍 {st.session_state.point_B['lat']:.6f}, {st.session_state.point_B['lng']:.6f}")
        else:
            st.warning("❌ **B点未设**")
        
        if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
            dist = calculate_distance(a_lat, a_lng, b_lat, b_lng)
            st.info(f"📏 航线距离: {dist:.1f} 米")
        
        st.info(f"✈️ 飞行高度: {st.session_state.flight_height} m")
        st.info(f"🗺️ 坐标系: {st.session_state.coord_system}")
        
        if st.session_state.obstacles:
            st.markdown("**🚧 障碍物列表**")
            for i, obs in enumerate(st.session_state.obstacles):
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.write(f"{i+1}. {obs['name']} ({obs['radius']}m)")
                with col_b:
                    if st.button("🗑️", key=f"del_{i}"):
                        st.session_state.obstacles.pop(i)
                        st.rerun()
    
    # 地图显示
    st.markdown("### 🛰️ 高德卫星地图")
    st.markdown("💡 鼠标滚轮缩放 | 拖拽平移 | 右上角全屏 | 右下角切换卫星图/路网图")
    
    try:
        amap = create_amap()
        folium_static(amap, width=1200, height=550)
    except Exception as e:
        st.error(f"地图加载失败: {str(e)}")
        st.info("请检查网络连接后刷新页面重试")

# ============================ 飞行监控页面 ============================

else:
    st.title("🛸 无人机心跳监测系统")
    st.markdown("模拟无人机每秒发送心跳包，3秒未收到自动报警")
    
    if st.session_state.running:
        st.markdown('<meta http-equiv="refresh" content="1">', unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🚀 启动模拟", use_container_width=True):
            reset_monitor()
            st.session_state.running = True
            add_heartbeat(1, time.time())
    with c2:
        if st.button("⏸️ 暂停/恢复", use_container_width=True):
            st.session_state.running = not st.session_state.running
    with c3:
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
            st.error(f"⚠️ 连接超时！已 {time.time() - st.session_state.last_ts:.1f} 秒未收到心跳")
        else:
            st.success("✅ 连接正常")
    
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.metric("📡 最新心跳序号", st.session_state.seq if st.session_state.seq > 0 else "—")
        status = "✈️ 飞行中" if st.session_state.running else "🛬 已停止"
        st.write(f"**状态: {status}**")
    with col_s2:
        if st.session_state.running and st.session_state.last_ts:
            since = time.time() - st.session_state.last_ts
            if since < 1:
                st.success(f"💓 最后心跳: {since:.1f}秒前")
            elif since < 3:
                st.warning(f"💓 最后心跳: {since:.1f}秒前")
            else:
                st.error(f"💔 最后心跳: {since:.1f}秒前")
    
    if st.session_state.records:
        df = pd.DataFrame(st.session_state.records, columns=["序号", "时间戳"])
        df["时间"] = pd.to_datetime(df["时间戳"], unit="s")
        df = df.sort_values("时间")
        st.subheader("📈 心跳序号变化趋势")
        st.line_chart(df.set_index("时间")["序号"], use_container_width=True)
        
        df["接收时间"] = df["时间戳"].apply(lambda x: datetime.fromtimestamp(x).strftime("%H:%M:%S"))
        st.subheader("📋 心跳记录（最近20条）")
        st.dataframe(df[["序号", "接收时间"]], use_container_width=True, height=400)
    else:
        st.info("📭 暂无数据，请点击「启动模拟」")

st.markdown("---")
st.markdown("© 2024 无人机地面站系统 | 高德卫星图 | WGS-84/GCJ-02 坐标转换 | 实时心跳监测")
