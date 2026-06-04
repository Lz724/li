import streamlit as st
import pandas as pd
import time
import math
from datetime datetime

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

def convert_coords(lat, lng, from_system, to_system="WGS-84"):
    if from_system == to_system:
        return lng, lat
    if from_system == "WGS-84" and to_system == "GCJ-02":
        return wgs84_to_gcj02(lng, lat)
    if from_system == "GCJ-02" and to_system == "WGS-84":
        return gcj02_to_wgs84(lng, lat)
    return lng, lat

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

# ---------------------------- 显示地图（使用表格+示意图）------------------------
def display_map_table():
    """显示地图数据的表格视图"""
    
    map_data = []
    
    if st.session_state.point_A["set"]:
        map_data.append({
            "类型": "起点A",
            "名称": "起点A",
            "纬度": st.session_state.point_A["lat"],
            "经度": st.session_state.point_A["lng"],
            "半径(m)": "-",
            "颜色": "绿色"
        })
    
    if st.session_state.point_B["set"]:
        map_data.append({
            "类型": "终点B",
            "名称": "终点B",
            "纬度": st.session_state.point_B["lat"],
            "经度": st.session_state.point_B["lng"],
            "半径(m)": "-",
            "颜色": "红色"
        })
    
    for obs in st.session_state.obstacles:
        map_data.append({
            "类型": "障碍物",
            "名称": obs["name"],
            "纬度": obs["lat"],
            "经度": obs["lng"],
            "半径(m)": obs["radius"],
            "颜色": "红色"
        })
    
    if map_data:
        df = pd.DataFrame(map_data)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("暂无数据，请设置起点/终点或添加障碍物")

def display_ascii_map():
    """显示ASCII风格的地图"""
    
    # 获取所有点的坐标
    all_lats = []
    all_lngs = []
    
    if st.session_state.point_A["set"]:
        all_lats.append(st.session_state.point_A["lat"])
        all_lngs.append(st.session_state.point_A["lng"])
    if st.session_state.point_B["set"]:
        all_lats.append(st.session_state.point_B["lat"])
        all_lngs.append(st.session_state.point_B["lng"])
    for obs in st.session_state.obstacles:
        all_lats.append(obs["lat"])
        all_lngs.append(obs["lng"])
    
    if not all_lats:
        st.info("请先设置起点或终点")
        return
    
    min_lat, max_lat = min(all_lats), max(all_lats)
    min_lng, max_lng = min(all_lngs), max(all_lngs)
    
    # 添加边距
    lat_margin = (max_lat - min_lat) * 0.1 if max_lat - min_lat > 0 else 0.001
    lng_margin = (max_lng - min_lng) * 0.1 if max_lng - min_lng > 0 else 0.001
    
    min_lat -= lat_margin
    max_lat += lat_margin
    min_lng -= lng_margin
    max_lng += lng_margin
    
    # 创建网格
    grid_size = 15
    lat_step = (max_lat - min_lat) / grid_size
    lng_step = (max_lng - min_lng) / grid_size
    
    map_grid = [["  " for _ in range(grid_size)] for _ in range(grid_size)]
    
    # 标记A点
    if st.session_state.point_A["set"]:
        lat_idx = int((st.session_state.point_A["lat"] - min_lat) / lat_step)
        lng_idx = int((st.session_state.point_A["lng"] - min_lng) / lng_step)
        if 0 <= lat_idx < grid_size and 0 <= lng_idx < grid_size:
            map_grid[lat_idx][lng_idx] = "A "
    
    # 标记B点
    if st.session_state.point_B["set"]:
        lat_idx = int((st.session_state.point_B["lat"] - min_lat) / lat_step)
        lng_idx = int((st.session_state.point_B["lng"] - min_lng) / lng_step)
        if 0 <= lat_idx < grid_size and 0 <= lng_idx < grid_size:
            map_grid[lat_idx][lng_idx] = "B "
    
    # 标记障碍物
    for obs in st.session_state.obstacles:
        lat_idx = int((obs["lat"] - min_lat) / lat_step)
        lng_idx = int((obs["lng"] - min_lng) / lng_step)
        if 0 <= lat_idx < grid_size and 0 <= lng_idx < grid_size:
            if map_grid[lat_idx][lng_idx] == "  ":
                map_grid[lat_idx][lng_idx] = "● "
    
    # 显示地图
    st.markdown("```")
    st.markdown(f"纬度范围: {min_lat:.6f} → {max_lat:.6f}")
    st.markdown(f"经度范围: {min_lng:.6f} → {max_lng:.6f}")
    st.markdown("")
    
    for i in range(grid_size - 1, -1, -1):
        row_str = "".join(map_grid[i])
        st.markdown(row_str)
    
    st.markdown("```")
    st.caption("图例: A=起点, B=终点, ●=障碍物")

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
st.sidebar.markdown("## 操作说明")
st.sidebar.markdown("- 📍 设置A/B点坐标")
st.sidebar.markdown("- 🚧 添加障碍物")
st.sidebar.markdown("- 🗺️ 查看表格/简图")
st.sidebar.markdown("- 💓 飞行监控页面")

# ============================ 航线规划 ============================
if page == "航线规划":
    st.title("🗺️ 航线规划")
    st.markdown("基于坐标的无人机航线规划系统 | 支持 WGS-84 / GCJ-02 坐标系转换")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("### 控制面板")
        
        st.markdown("#### 起点A")
        a_lat = st.number_input("纬度", value=st.session_state.point_A["lat"], format="%.6f", key="a_lat")
        a_lng = st.number_input("经度", value=st.session_state.point_A["lng"], format="%.6f", key="a_lng")
        if st.button("📍 设置A点", use_container_width=True):
            st.session_state.point_A = {"lat": a_lat, "lng": a_lng, "set": True}
            st.success("✅ 起点A已设置")
            st.rerun()
        
        st.markdown("#### 终点B")
        b_lat = st.number_input("纬度", value=st.session_state.point_B["lat"], format="%.6f", key="b_lat")
        b_lng = st.number_input("经度", value=st.session_state.point_B["lng"], format="%.6f", key="b_lng")
        if st.button("🎯 设置B点", use_container_width=True):
            st.session_state.point_B = {"lat": b_lat, "lng": b_lng, "set": True}
            st.success("✅ 终点B已设置")
            st.rerun()
        
        st.markdown("#### 飞行参数")
        st.session_state.flight_height = st.number_input("飞行高度 (m)", value=st.session_state.flight_height, step=5.0)
        
        st.markdown("#### 障碍物管理")
        with st.expander("➕ 添加新障碍物", expanded=False):
            obs_name = st.text_input("名称", "新障碍物")
            col_o1, col_o2 = st.columns(2)
            with col_o1:
                obs_lat = st.number_input("纬度", value=32.2330, format="%.6f", key="obs_lat")
            with col_o2:
                obs_lng = st.number_input("经度", value=118.7495, format="%.6f", key="obs_lng")
            obs_radius = st.number_input("半径(m)", value=25, step=5, key="obs_radius")
            if st.button("✅ 确认添加", key="add_obs"):
                st.session_state.obstacles.append({
                    "lat": obs_lat, "lng": obs_lng,
                    "radius": obs_radius, "name": obs_name
                })
                st.success(f"已添加: {obs_name}")
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
            st.info(f"📏 **航线距离**: {dist:.1f} 米")
        
        st.info(f"✈️ **飞行高度**: {st.session_state.flight_height} m")
        st.info(f"🗺️ **当前坐标系**: {st.session_state.coord_system}")
        
        if st.session_state.obstacles:
            st.markdown("**🚧 障碍物列表**")
            for i, obs in enumerate(st.session_state.obstacles):
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.write(f"{i+1}. {obs['name']} (半径:{obs['radius']}m)")
                with col_b:
                    if st.button("🗑️", key=f"del_{i}"):
                        st.session_state.obstacles.pop(i)
                        st.rerun()
    
    # 地图显示（使用表格和简图）
    st.markdown("### 🗺️ 地图视图")
    
    tab1, tab2 = st.tabs(["📊 表格视图", "🗺️ 简图视图"])
    
    with tab1:
        display_map_table()
    
    with tab2:
        display_ascii_map()
    
    # 航线信息
    if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
        st.markdown("### ✈️ 航线信息")
        st.markdown(f"- 起点A → 终点B")
        st.markdown(f"- 直线距离: **{dist:.1f} 米**")
        st.markdown(f"- 飞行高度: **{st.session_state.flight_height} 米**")
    
    # 使用说明
    with st.expander("📖 使用说明", expanded=False):
        st.markdown("""
        ### 功能说明
        
        **1. 设置起点/终点**
        - 输入经纬度坐标，点击"设置A点"或"设置B点"
        - 支持 WGS-84 和 GCJ-02 坐标系
        
        **2. 障碍物管理**
        - 预设校园障碍物（教学楼、图书馆、实验楼、食堂、体育馆）
        - 可添加/删除障碍物
        
        **3. 坐标系转换**
        - WGS-84: GPS标准坐标
        - GCJ-02: 高德/百度地图坐标
        
        **4. 地图视图**
        - 表格视图: 列表显示所有点位
        - 简图视图: ASCII风格相对位置图
        """)

# ============================ 飞行监控 ============================
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
st.markdown("© 无人机地面站系统 | 支持 WGS-84/GCJ-02 坐标转换 | 实时心跳监测")
