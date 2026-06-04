import streamlit as st
import pandas as pd
import time
import math
from datetime import datetime
import pydeck as pdk
import numpy as np

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
    """将坐标转换为 WGS-84 用于地图显示"""
    if src_system == "WGS-84":
        return lng, lat
    else:
        return gcj02_to_wgs84(lng, lat)

# ---------------------------- 距离计算函数 ----------------------------
def calculate_distance(lat1, lng1, lat2, lng2):
    """使用 Haversine 公式计算两点间距离（单位：米）"""
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
    # 飞行监控相关
    if "running" not in st.session_state:
        st.session_state.running = False
        st.session_state.seq = 0
        st.session_state.last_ts = None
        st.session_state.records = []
        st.session_state.alert_msg = ""
    
    # 航线规划相关
    if "coord_system" not in st.session_state:
        st.session_state.coord_system = "GCJ-02"
    
    if "point_A" not in st.session_state:
        st.session_state.point_A = {"lat": 32.2322, "lng": 118.749, "set": False}
    
    if "point_B" not in st.session_state:
        st.session_state.point_B = {"lat": 32.2343, "lng": 118.749, "set": False}
    
    if "flight_height" not in st.session_state:
        st.session_state.flight_height = 50.0
    
    if "obstacles" not in st.session_state:
        # 校园内障碍物（WGS-84 坐标）
        st.session_state.obstacles = [
            {"lat": 32.2328, "lng": 118.7485, "radius": 30, "name": "教学楼"},
            {"lat": 32.2335, "lng": 118.7492, "radius": 35, "name": "图书馆"},
            {"lat": 32.2330, "lng": 118.7500, "radius": 28, "name": "实验楼"},
            {"lat": 32.2325, "lng": 118.7495, "radius": 25, "name": "食堂"},
            {"lat": 32.2318, "lng": 118.7482, "radius": 22, "name": "体育馆"},
        ]
    
    if "map_zoom" not in st.session_state:
        st.session_state.map_zoom = 16
    
    if "map_pitch" not in st.session_state:
        st.session_state.map_pitch = 0  # 0度表示2D俯视角度

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

# ---------------------------- 卫星地图创建函数（使用 pydeck + 卫星瓦片）------------------------
def create_satellite_map():
    """创建使用卫星影像的 pydeck 地图"""
    
    layers = []
    scatter_data = []
    
    # 获取 A、B 点的 WGS-84 坐标用于地图显示
    a_wgs_lng, a_wgs_lat = None, None
    b_wgs_lng, b_wgs_lat = None, None
    
    # 添加 A 点（绿色）
    if st.session_state.point_A["set"]:
        a_wgs_lng, a_wgs_lat = convert_to_wgs84(
            st.session_state.point_A["lat"], 
            st.session_state.point_A["lng"], 
            st.session_state.coord_system
        )
        scatter_data.append({
            "lng": a_wgs_lng,
            "lat": a_wgs_lat,
            "type": "A",
            "color": [0, 255, 0],
            "size": 100,
            "name": f"起点A\n纬度: {st.session_state.point_A['lat']:.6f}\n经度: {st.session_state.point_A['lng']:.6f}"
        })
    
    # 添加 B 点（红色）
    if st.session_state.point_B["set"]:
        b_wgs_lng, b_wgs_lat = convert_to_wgs84(
            st.session_state.point_B["lat"], 
            st.session_state.point_B["lng"], 
            st.session_state.coord_system
        )
        scatter_data.append({
            "lng": b_wgs_lng,
            "lat": b_wgs_lat,
            "type": "B",
            "color": [255, 0, 0],
            "size": 100,
            "name": f"终点B\n纬度: {st.session_state.point_B['lat']:.6f}\n经度: {st.session_state.point_B['lng']:.6f}"
        })
    
    # 添加障碍物（红色半透明）
    for obs in st.session_state.obstacles:
        # 障碍物坐标转换为 WGS-84
        obs_wgs_lng, obs_wgs_lat = convert_to_wgs84(obs["lat"], obs["lng"], "WGS-84")
        scatter_data.append({
            "lng": obs_wgs_lng,
            "lat": obs_wgs_lat,
            "type": "obstacle",
            "color": [255, 0, 0],
            "size": obs["radius"] * 2,
            "name": f"{obs['name']}\n半径: {obs['radius']}m"
        })
    
    # 散点图层
    if scatter_data:
        scatter_layer = pdk.Layer(
            "ScatterplotLayer",
            data=scatter_data,
            get_position=["lng", "lat"],
            get_radius="size",
            get_fill_color="color",
            get_line_color="color",
            pickable=True,
            auto_highlight=True,
            radius_scale=1,
            radius_min_pixels=5,
            radius_max_pixels=80
        )
        layers.append(scatter_layer)
    
    # 航线图层
    if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
        # 地面航线（黄色）
        line_data = [{
            "start_lng": a_wgs_lng,
            "start_lat": a_wgs_lat,
            "end_lng": b_wgs_lng,
            "end_lat": b_wgs_lat
        }]
        
        line_layer = pdk.Layer(
            "LineLayer",
            data=line_data,
            get_source_position=["start_lng", "start_lat"],
            get_target_position=["end_lng", "end_lat"],
            get_color=[255, 255, 0],
            get_width=5,
            pickable=True,
            tooltip=f"航线 | 高度: {st.session_state.flight_height}m"
        )
        layers.append(line_layer)
    
    # 确定地图中心
    if st.session_state.point_A["set"]:
        center_lng, center_lat = a_wgs_lng, a_wgs_lat
    elif st.session_state.point_B["set"]:
        center_lng, center_lat = b_wgs_lng, b_wgs_lat
    else:
        center_lng, center_lat = 118.7492, 32.2332
    
    # 视图设置（2D俯视角度，方便查看卫星图）
    view_state = pdk.ViewState(
        longitude=center_lng,
        latitude=center_lat,
        zoom=st.session_state.map_zoom,
        pitch=st.session_state.map_pitch,
        bearing=0
    )
    
    # 使用卫星地图样式
    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        map_style="satellite",  # 使用卫星地图
        tooltip={"text": "{name}"}
    )
    
    return deck

# ---------------------------- 页面配置 ----------------------------
st.set_page_config(page_title="无人机地面站系统", layout="wide")

# 侧边栏导航
st.sidebar.title("导航")
page = st.sidebar.radio("功能页面", ["航线规划", "飞行监控"])

# 侧边栏全局设置
st.sidebar.markdown("---")
st.sidebar.subheader("坐标系设置")
coord_sys = st.sidebar.selectbox(
    "输入坐标系",
    ["WGS-84", "GCJ-02(高德/百度)"],
    index=0 if st.session_state.coord_system == "WGS-84" else 1
)
st.session_state.coord_system = coord_sys.split("(")[0]

st.sidebar.subheader("地图控制")
st.session_state.map_zoom = st.sidebar.slider("缩放级别", 14, 20, st.session_state.map_zoom, 1)
st.session_state.map_pitch = st.sidebar.slider("倾斜角度", 0, 85, st.session_state.map_pitch, 5)

st.sidebar.info("""
💡 **地图操作说明**:
- 🖱️ 鼠标左键拖拽: 平移地图
- 🖱️ 鼠标右键拖拽: 旋转视角
- 🔍 鼠标滚轮: 缩放地图
- 🗺️ 底图: 卫星影像
""")

# ============================ 航线规划页面 ============================
if page == "航线规划":
    st.title("🗺️ 航线规划")
    st.markdown("基于卫星影像的无人机航线规划系统 | 支持 WGS-84 / GCJ-02 坐标系转换")
    
    # 主控制面板
    col1, col2 = st.columns([1, 1.2])
    
    with col1:
        st.subheader("控制面板")
        
        # 起点A
        st.write("#### 起点A")
        a_lat = st.number_input(
            "纬度",
            value=st.session_state.point_A["lat"],
            format="%.6f",
            key="a_lat"
        )
        a_lng = st.number_input(
            "经度",
            value=st.session_state.point_A["lng"],
            format="%.6f",
            key="a_lng"
        )
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("📍 设置A点", use_container_width=True):
                st.session_state.point_A = {"lat": a_lat, "lng": a_lng, "set": True}
                st.success("✅ 起点A已设置")
                st.rerun()
        with col_btn2:
            if st.button("🗑️ 清除A点", use_container_width=True):
                st.session_state.point_A["set"] = False
                st.rerun()
        
        # 终点B
        st.write("#### 终点B")
        b_lat = st.number_input(
            "纬度",
            value=st.session_state.point_B["lat"],
            format="%.6f",
            key="b_lat"
        )
        b_lng = st.number_input(
            "经度",
            value=st.session_state.point_B["lng"],
            format="%.6f",
            key="b_lng"
        )
        col_btn3, col_btn4 = st.columns(2)
        with col_btn3:
            if st.button("🎯 设置B点", use_container_width=True):
                st.session_state.point_B = {"lat": b_lat, "lng": b_lng, "set": True}
                st.success("✅ 终点B已设置")
                st.rerun()
        with col_btn4:
            if st.button("🗑️ 清除B点", use_container_width=True):
                st.session_state.point_B["set"] = False
                st.rerun()
        
        # 飞行参数
        st.write("#### 飞行参数")
        height = st.number_input(
            "设定飞行高度 (m)",
            value=st.session_state.flight_height,
            step=5.0,
            help="无人机飞行的高度"
        )
        st.session_state.flight_height = height
        
        # 障碍物管理
        st.write("#### 障碍物管理")
        with st.expander("➕ 添加新障碍物", expanded=False):
            obs_name = st.text_input("障碍物名称", "新障碍物")
            col_obs1, col_obs2 = st.columns(2)
            with col_obs1:
                obs_lat = st.number_input("纬度", value=32.2330, format="%.6f", key="obs_lat")
            with col_obs2:
                obs_lng = st.number_input("经度", value=118.7495, format="%.6f", key="obs_lng")
            obs_radius = st.number_input("半径 (m)", value=25, step=5, key="obs_radius")
            if st.button("✅ 确认添加", key="add_obs"):
                st.session_state.obstacles.append({
                    "lat": obs_lat,
                    "lng": obs_lng,
                    "radius": obs_radius,
                    "name": obs_name
                })
                st.success(f"已添加障碍物: {obs_name}")
                st.rerun()
    
    with col2:
        st.subheader("系统状态")
        
        # 状态显示卡片
        if st.session_state.point_A["set"]:
            st.success(f"✅ **A点已设**\n\n📍 纬度: {st.session_state.point_A['lat']:.6f}\n📍 经度: {st.session_state.point_A['lng']:.6f}")
        else:
            st.warning("❌ **A点未设** - 请输入坐标并点击设置")
        
        if st.session_state.point_B["set"]:
            st.success(f"✅ **B点已设**\n\n📍 纬度: {st.session_state.point_B['lat']:.6f}\n📍 经度: {st.session_state.point_B['lng']:.6f}")
        else:
            st.warning("❌ **B点未设** - 请输入坐标并点击设置")
        
        st.info(f"✈️ **飞行高度**: {st.session_state.flight_height} m")
        st.info(f"🗺️ **当前坐标系**: {st.session_state.coord_system}")
        
        # 计算航线距离
        if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
            distance = calculate_distance(
                st.session_state.point_A["lat"], st.session_state.point_A["lng"],
                st.session_state.point_B["lat"], st.session_state.point_B["lng"]
            )
            st.success(f"📏 **航线距离**: {distance:.1f} 米")
        
        # 障碍物列表
        if st.session_state.obstacles:
            st.write("**🚧 障碍物列表**")
            for i, obs in enumerate(st.session_state.obstacles):
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.write(f"{i+1}. {obs['name']} (半径:{obs['radius']}m)")
                    st.caption(f"   {obs['lat']:.6f}, {obs['lng']:.6f}")
                with col_b:
                    if st.button("🗑️", key=f"del_{i}"):
                        st.session_state.obstacles.pop(i)
                        st.rerun()
    
    # 卫星地图显示
    st.subheader("🛰️ 卫星地图")
    st.markdown("💡 **操作提示**：")
    st.markdown("- 🔍 **鼠标滚轮**: 缩放地图 | 🖱️ **鼠标左键拖拽**: 平移地图 | 🖱️ **鼠标右键拖拽**: 旋转视角")
    st.markdown("- 🟢 **绿色点**: 起点A | 🔴 **红色点**: 终点B/障碍物 | 🟡 **黄色线**: 规划航线")
    st.markdown("- 底图使用 **卫星影像**，可放大查看校园建筑细节")
    
    # 创建并显示地图
    try:
        deck = create_satellite_map()
        st.pydeck_chart(deck, use_container_width=True)
    except Exception as e:
        st.error(f"地图加载出错: {str(e)}")
        st.info("请刷新页面重试，或检查网络连接")
    
    # 使用说明
    with st.expander("📖 详细使用说明", expanded=False):
        st.markdown("""
        ### 🎯 功能说明
        
        **1. 设置起点/终点**
        - 在左侧控制面板输入经纬度坐标
        - 点击"设置A点"或"设置B点"按钮
        - 支持 WGS-84 和 GCJ-02 两种坐标系
        
        **2. 飞行参数**
        - 设置飞行高度（单位：米）
        - 航线会显示在规划路径上
        
        **3. 障碍物管理**
        - 系统预设了校园内的障碍物（教学楼、图书馆、实验楼、食堂、体育馆）
        - 可以添加新的障碍物（需要输入名称、经纬度、半径）
        - 可以删除现有障碍物
        
        **4. 坐标系转换**
        - **WGS-84**：国际标准坐标系（GPS使用）
        - **GCJ-02**：高德/百度地图使用的坐标系（火星坐标系）
        - 系统会自动转换坐标进行显示
        
        **5. 卫星地图操作**
        - **鼠标左键拖拽**：平移地图
        - **鼠标右键拖拽**：旋转3D视角
        - **鼠标滚轮**：缩放地图
        - **鼠标悬停**：查看详细信息
        
        **6. 地图元素说明**
        - 🟢 **绿色点**：起点A
        - 🔴 **红色点**：终点B
        - 🟡 **黄色线**：规划航线
        - 🔴 **红色圆圈**：障碍物（显示名称和半径）
        """)

# ============================ 飞行监控页面 ============================
else:
    st.title("🛸 无人机心跳监测系统")
    st.markdown("模拟无人机每秒发送心跳包，地面站实时监测并绘制折线图，3秒未收到自动报警")
    
    # 自动刷新
    if st.session_state.running:
        st.markdown('<meta http-equiv="refresh" content="1">', unsafe_allow_html=True)
    
    # 控制按钮
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
    
    # 心跳生成逻辑
    if st.session_state.running:
        now = time.time()
        last = st.session_state.last_ts
        if last is None:
            add_heartbeat(1, now)
        else:
            diff = now - last
            if diff >= 1.0:
                n = min(int(diff), 5)
                for i in range(n):
                    new_seq = st.session_state.seq + 1
                    sim_ts = last + (i + 1)
                    add_heartbeat(new_seq, sim_ts)
        
        # 超时检测
        if st.session_state.last_ts and (time.time() - st.session_state.last_ts) > 3.0:
            st.session_state.alert_msg = f"⚠️ 连接超时！已 {time.time() - st.session_state.last_ts:.1f} 秒未收到心跳"
        else:
            st.session_state.alert_msg = ""
    
    # 状态显示
    col_status, col_alert = st.columns(2)
    with col_status:
        st.metric("📡 最新心跳序号", st.session_state.seq if st.session_state.seq > 0 else "—")
        status_text = "✈️ 飞行中" if st.session_state.running else "🛬 已停止"
        st.write(f"**无人机状态：{status_text}**")
    
    with col_alert:
        if st.session_state.alert_msg:
            st.error(st.session_state.alert_msg)
        else:
            st.success("✅ 连接正常")
    
    # 实时心跳指示器
    if st.session_state.running and st.session_state.last_ts:
        time_since_last = time.time() - st.session_state.last_ts
        if time_since_last < 1:
            st.success(f"💓 最后心跳: {time_since_last:.1f}秒前")
        elif time_since_last < 3:
            st.warning(f"💓 最后心跳: {time_since_last:.1f}秒前")
        else:
            st.error(f"💔 最后心跳: {time_since_last:.1f}秒前")
    
    # 折线图
    if st.session_state.records:
        df = pd.DataFrame(st.session_state.records, columns=["序号", "时间戳"])
        df["时间"] = pd.to_datetime(df["时间戳"], unit="s")
        df = df.sort_values("时间")
        st.subheader("📈 心跳序号变化趋势")
        st.line_chart(df.set_index("时间")["序号"], use_container_width=True)
    else:
        st.info("📭 尚未收到任何心跳包，请点击「启动模拟」")
    
    # 表格
    if st.session_state.records:
        df_table = pd.DataFrame(st.session_state.records, columns=["心跳序号", "时间戳"])
        df_table["接收时间"] = df_table["时间戳"].apply(lambda x: datetime.fromtimestamp(x).strftime("%H:%M:%S"))
        df_table["延迟(ms)"] = df_table["时间戳"].diff().fillna(0) * 1000
        df_table = df_table[["心跳序号", "接收时间", "延迟(ms)"]]
        st.subheader("📋 心跳包记录（最近20条）")
        st.dataframe(df_table, use_container_width=True, height=400)
    else:
        st.info("📋 暂无记录")

# 底部信息
st.markdown("---")
st.markdown("© 2024 无人机地面站系统 | 底图: 卫星影像 | 支持 WGS-84/GCJ-02 坐标系转换 | 实时心跳监测")
