import streamlit as st
import pandas as pd
import time
import math
from datetime import datetime
import pydeck as pdk

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

def convert_to_wgs84(lat, lng, src_system):
    if src_system == "WGS-84":
        return lng, lat
    else:
        return gcj02_to_wgs84(lng, lat)

# ---------------------------- 距离计算 ----------------------------
def calculate_distance(lat1, lng1, lat2, lng2):
    R = 6371000
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# ---------------------------- 初始化 ----------------------------
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

# ---------------------------- 心跳函数 ----------------------------
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

# ---------------------------- 创建地图 ----------------------------
def create_map():
    scatter_data = []
    
    if st.session_state.point_A["set"]:
        lng, lat = convert_to_wgs84(
            st.session_state.point_A["lat"], 
            st.session_state.point_A["lng"], 
            st.session_state.coord_system
        )
        scatter_data.append({
            "lng": lng, "lat": lat, "color": [0, 255, 0], "size": 80,
            "name": f"起点A\n{st.session_state.point_A['lat']:.6f}, {st.session_state.point_A['lng']:.6f}"
        })
    
    if st.session_state.point_B["set"]:
        lng, lat = convert_to_wgs84(
            st.session_state.point_B["lat"], 
            st.session_state.point_B["lng"], 
            st.session_state.coord_system
        )
        scatter_data.append({
            "lng": lng, "lat": lat, "color": [255, 0, 0], "size": 80,
            "name": f"终点B\n{st.session_state.point_B['lat']:.6f}, {st.session_state.point_B['lng']:.6f}"
        })
    
    for obs in st.session_state.obstacles:
        lng, lat = convert_to_wgs84(obs["lat"], obs["lng"], "WGS-84")
        scatter_data.append({
            "lng": lng, "lat": lat, "color": [255, 0, 0], "size": obs["radius"] * 2,
            "name": f"{obs['name']}\n半径: {obs['radius']}m"
        })
    
    layers = []
    if scatter_data:
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=scatter_data,
            get_position=["lng", "lat"],
            get_radius="size",
            get_fill_color="color",
            pickable=True,
            radius_min_pixels=5,
            radius_max_pixels=60
        ))
    
    if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
        a_lng, a_lat = convert_to_wgs84(
            st.session_state.point_A["lat"], 
            st.session_state.point_A["lng"], 
            st.session_state.coord_system
        )
        b_lng, b_lat = convert_to_wgs84(
            st.session_state.point_B["lat"], 
            st.session_state.point_B["lng"], 
            st.session_state.coord_system
        )
        layers.append(pdk.Layer(
            "LineLayer",
            data=[{"start": [a_lng, a_lat], "end": [b_lng, b_lat]}],
            get_source_position="start",
            get_target_position="end",
            get_color=[255, 255, 0],
            get_width=4
        ))
    
    if st.session_state.point_A["set"]:
        center_lng, center_lat = convert_to_wgs84(
            st.session_state.point_A["lat"], 
            st.session_state.point_A["lng"], 
            st.session_state.coord_system
        )
    elif st.session_state.point_B["set"]:
        center_lng, center_lat = convert_to_wgs84(
            st.session_state.point_B["lat"], 
            st.session_state.point_B["lng"], 
            st.session_state.coord_system
        )
    else:
        center_lng, center_lat = 118.7492, 32.2332
    
    return pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(
            longitude=center_lng, latitude=center_lat,
            zoom=st.session_state.map_zoom, pitch=0, bearing=0
        ),
        map_style="light",
        tooltip={"text": "{name}"}
    )

# ---------------------------- 页面 ----------------------------
st.set_page_config(page_title="无人机地面站系统", layout="wide")

st.sidebar.markdown("# 导航")
page = st.sidebar.radio("功能页面", ["航线规划", "飞行监控"])

st.sidebar.markdown("---")
st.sidebar.markdown("# 坐标系设置")
coord_sys = st.sidebar.selectbox(
    "输入坐标系", ["WGS-84", "GCJ-02(高德/百度)"],
    index=0 if st.session_state.coord_system == "WGS-84" else 1
)
st.session_state.coord_system = coord_sys.split("(")[0]

st.sidebar.markdown("---")
st.sidebar.markdown("# 地图控制")
st.session_state.map_zoom = st.sidebar.slider("缩放级别", 14, 20, st.session_state.map_zoom, 1)

st.sidebar.markdown("---")
st.sidebar.markdown("## 操作说明")
st.sidebar.markdown("- 🖱️ 左键拖拽: 平移")
st.sidebar.markdown("- 🖱️ 右键拖拽: 旋转")
st.sidebar.markdown("- 🔍 滚轮: 缩放")
st.sidebar.markdown("- 🟢 绿色: 起点A")
st.sidebar.markdown("- 🔴 红色: 终点B/障碍物")
st.sidebar.markdown("- 🟡 黄色: 航线")

# ============================ 航线规划 ============================
if page == "航线规划":
    st.title("🗺️ 航线规划")
    
    col1, col2 = st.columns([1, 1.2])
    
    with col1:
        st.markdown("### 控制面板")
        
        st.markdown("#### 起点A")
        a_lat = st.number_input("纬度", value=st.session_state.point_A["lat"], format="%.6f", key="a_lat")
        a_lng = st.number_input("经度", value=st.session_state.point_A["lng"], format="%.6f", key="a_lng")
        if st.button("📍 设置A点", use_container_width=True):
            st.session_state.point_A = {"lat": a_lat, "lng": a_lng, "set": True}
            st.rerun()
        
        st.markdown("#### 终点B")
        b_lat = st.number_input("纬度", value=st.session_state.point_B["lat"], format="%.6f", key="b_lat")
        b_lng = st.number_input("经度", value=st.session_state.point_B["lng"], format="%.6f", key="b_lng")
        if st.button("🎯 设置B点", use_container_width=True):
            st.session_state.point_B = {"lat": b_lat, "lng": b_lng, "set": True}
            st.rerun()
        
        st.markdown("#### 飞行参数")
        st.session_state.flight_height = st.number_input("飞行高度 (m)", value=st.session_state.flight_height, step=5.0)
        
        st.markdown("#### 障碍物")
        with st.expander("➕ 添加障碍物"):
            obs_name = st.text_input("名称", "新障碍物")
            obs_lat = st.number_input("纬度", value=32.2330, format="%.6f")
            obs_lng = st.number_input("经度", value=118.7495, format="%.6f")
            obs_radius = st.number_input("半径(m)", value=25, step=5)
            if st.button("✅ 添加"):
                st.session_state.obstacles.append({"lat": obs_lat, "lng": obs_lng, "radius": obs_radius, "name": obs_name})
                st.rerun()
    
    with col2:
        st.markdown("### 系统状态")
        
        if st.session_state.point_A["set"]:
            st.success(f"✅ A点已设: {st.session_state.point_A['lat']:.6f}, {st.session_state.point_A['lng']:.6f}")
        else:
            st.warning("❌ A点未设")
        
        if st.session_state.point_B["set"]:
            st.success(f"✅ B点已设: {st.session_state.point_B['lat']:.6f}, {st.session_state.point_B['lng']:.6f}")
        else:
            st.warning("❌ B点未设")
        
        if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
            dist = calculate_distance(a_lat, a_lng, b_lat, b_lng)
            st.info(f"📏 航线距离: {dist:.1f} 米")
        
        st.info(f"✈️ 飞行高度: {st.session_state.flight_height} m")
        st.info(f"🗺️ 坐标系: {st.session_state.coord_system}")
        
        if st.session_state.obstacles:
            st.markdown("**障碍物列表**")
            for i, obs in enumerate(st.session_state.obstacles):
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.write(f"{i+1}. {obs['name']} ({obs['radius']}m)")
                with col_b:
                    if st.button("🗑️", key=f"del_{i}"):
                        st.session_state.obstacles.pop(i)
                        st.rerun()
    
    st.markdown("### 🗺️ 地图")
    st.markdown("💡 鼠标左键拖拽平移 | 右键拖拽旋转 | 滚轮缩放")
    
    try:
        deck = create_map()
        st.pydeck_chart(deck, use_container_width=True)
    except Exception as e:
        st.error(f"地图加载失败: {str(e)}")

# ============================ 飞行监控 ============================
else:
    st.title("🛸 无人机心跳监测系统")
    
    if st.session_state.running:
        st.markdown('<meta http-equiv="refresh" content="1">', unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🚀 启动", use_container_width=True):
            reset_monitor()
            st.session_state.running = True
            add_heartbeat(1, time.time())
    with c2:
        if st.button("⏸️ 暂停/恢复", use_container_width=True):
            st.session_state.running = not st.session_state.running
    with c3:
        if st.button("🛑 停止", use_container_width=True):
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
            st.success("✅ 正常")
    
    st.metric("最新心跳序号", st.session_state.seq or "—")
    
    if st.session_state.records:
        df = pd.DataFrame(st.session_state.records, columns=["序号", "时间戳"])
        df["时间"] = pd.to_datetime(df["时间戳"], unit="s")
        st.line_chart(df.set_index("时间")["序号"])
        df["接收时间"] = df["时间戳"].apply(lambda x: datetime.fromtimestamp(x).strftime("%H:%M:%S"))
        st.dataframe(df[["序号", "接收时间"]], use_container_width=True)
    else:
        st.info("暂无数据，请点击启动")

st.markdown("---")
st.markdown("© 无人机地面站 | WGS-84/GCJ-02 坐标转换")
