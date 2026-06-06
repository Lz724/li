"""
无人机地面站系统 - 纯Streamlit版本
无需任何地图库，使用表格和简化示意图显示
"""

import streamlit as st
import pandas as pd
import time
import math
from datetime import datetime

# ============================ 坐标系转换算法 ============================

def transform_lat(lng, lat):
    """GCJ-02 坐标转换辅助函数"""
    ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + 0.1 * lng * lat + 0.2 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * math.pi) + 40.0 * math.sin(lat / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * math.pi) + 320 * math.sin(lat * math.pi / 30.0)) * 2.0 / 3.0
    return ret

def transform_lng(lng, lat):
    """GCJ-02 坐标转换辅助函数"""
    ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + 0.1 * lng * lat + 0.1 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lng * math.pi) + 40.0 * math.sin(lng / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lng / 12.0 * math.pi) + 300.0 * math.sin(lng / 30.0 * math.pi)) * 2.0 / 3.0
    return ret

def wgs84_to_gcj02(lng, lat):
    """WGS-84 转 GCJ-02"""
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
    """GCJ-02 转 WGS-84"""
    if out_of_china(lng, lat):
        return lng, lat
    dlng, dlat = wgs84_to_gcj02(lng, lat)
    return lng * 2 - dlng, lat * 2 - dlat

def out_of_china(lng, lat):
    """判断是否在中国境外"""
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)

def convert_for_display(lat, lng, src_system):
    """转换为地图显示坐标（高德使用 GCJ-02）"""
    if src_system == "WGS-84":
        return wgs84_to_gcj02(lng, lat)
    else:
        return lng, lat

# ============================ 距离计算 ============================

def calculate_distance(lat1, lng1, lat2, lng2):
    """使用 Haversine 公式计算两点间距离（米）"""
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
    """初始化 session state 变量"""
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

init_state()

# ============================ 心跳监控函数 ============================

def add_heartbeat(seq, ts):
    """添加心跳记录"""
    st.session_state.records.insert(0, (seq, ts))
    if len(st.session_state.records) > 20:
        st.session_state.records.pop()
    st.session_state.seq = seq
    st.session_state.last_ts = ts

def reset_monitor():
    """重置监控状态"""
    st.session_state.running = False
    st.session_state.seq = 0
    st.session_state.last_ts = None
    st.session_state.records = []
    st.session_state.alert_msg = ""

# ============================ 显示简化地图（ASCII风格） ============================

def display_ascii_map():
    """显示ASCII风格的地图示意图"""
    
    # 获取所有点的坐标
    all_lats = []
    all_lngs = []
    points_info = []
    
    if st.session_state.point_A["set"]:
        all_lats.append(st.session_state.point_A["lat"])
        all_lngs.append(st.session_state.point_A["lng"])
        points_info.append({"type": "A", "lat": st.session_state.point_A["lat"], "lng": st.session_state.point_A["lng"], "name": "起点A"})
    
    if st.session_state.point_B["set"]:
        all_lats.append(st.session_state.point_B["lat"])
        all_lngs.append(st.session_state.point_B["lng"])
        points_info.append({"type": "B", "lat": st.session_state.point_B["lat"], "lng": st.session_state.point_B["lng"], "name": "终点B"})
    
    for obs in st.session_state.obstacles:
        all_lats.append(obs["lat"])
        all_lngs.append(obs["lng"])
        points_info.append({"type": "O", "lat": obs["lat"], "lng": obs["lng"], "name": obs["name"]})
    
    if not all_lats:
        st.info("请先设置起点或终点")
        return
    
    # 计算范围
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
    grid_size = 20
    lat_step = (max_lat - min_lat) / grid_size
    lng_step = (max_lng - min_lng) / grid_size
    
    map_grid = [["  " for _ in range(grid_size)] for _ in range(grid_size)]
    
    # 标记点
    for point in points_info:
        lat_idx = int((point["lat"] - min_lat) / lat_step)
        lng_idx = int((point["lng"] - min_lng) / lng_step)
        if 0 <= lat_idx < grid_size and 0 <= lng_idx < grid_size:
            if point["type"] == "A":
                map_grid[lat_idx][lng_idx] = "A "
            elif point["type"] == "B":
                map_grid[lat_idx][lng_idx] = "B "
            else:
                if map_grid[lat_idx][lng_idx] == "  ":
                    map_grid[lat_idx][lng_idx] = "● "
    
    # 显示地图
    st.markdown("### 🗺️ 相对位置示意图")
    st.markdown("```")
    st.markdown(f"纬度范围: {min_lat:.6f} → {max_lat:.6f}")
    st.markdown(f"经度范围: {min_lng:.6f} → {max_lng:.6f}")
    st.markdown("")
    
    # 添加北向指示
    st.markdown("北 ↑")
    
    # 显示网格地图
    for i in range(grid_size - 1, -1, -1):
        row_str = "".join(map_grid[i])
        st.markdown(row_str)
    
    st.markdown("```")
    st.caption("图例: A=起点, B=终点, ●=障碍物 | 北在上方")
    
    # 添加方位说明
    col_dir1, col_dir2, col_dir3, col_dir4 = st.columns(4)
    with col_dir1:
        st.markdown("⬆️ **北**")
    with col_dir2:
        st.markdown("⬅️ **西**")
    with col_dir3:
        st.markdown("➡️ **东**")
    with col_dir4:
        st.markdown("⬇️ **南**")

def display_coordinate_table():
    """显示坐标表格"""
    
    coord_data = []
    
    if st.session_state.point_A["set"]:
        # 转换坐标
        gcj_lng, gcj_lat = convert_for_display(
            st.session_state.point_A["lat"], 
            st.session_state.point_A["lng"], 
            st.session_state.coord_system
        )
        coord_data.append({
            "类型": "起点A",
            "名称": "起点A",
            "原始纬度": st.session_state.point_A["lat"],
            "原始经度": st.session_state.point_A["lng"],
            "显示纬度(GCJ-02)": gcj_lat,
            "显示经度(GCJ-02)": gcj_lng
        })
    
    if st.session_state.point_B["set"]:
        gcj_lng, gcj_lat = convert_for_display(
            st.session_state.point_B["lat"], 
            st.session_state.point_B["lng"], 
            st.session_state.coord_system
        )
        coord_data.append({
            "类型": "终点B",
            "名称": "终点B",
            "原始纬度": st.session_state.point_B["lat"],
            "原始经度": st.session_state.point_B["lng"],
            "显示纬度(GCJ-02)": gcj_lat,
            "显示经度(GCJ-02)": gcj_lng
        })
    
    for obs in st.session_state.obstacles:
        gcj_lng, gcj_lat = convert_for_display(obs["lat"], obs["lng"], "WGS-84")
        coord_data.append({
            "类型": "障碍物",
            "名称": obs["name"],
            "原始纬度": obs["lat"],
            "原始经度": obs["lng"],
            "显示纬度(GCJ-02)": gcj_lat,
            "显示经度(GCJ-02)": gcj_lng,
            "半径(m)": obs["radius"]
        })
    
    if coord_data:
        df = pd.DataFrame(coord_data)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("暂无数据")

# ============================ 页面配置 ============================

st.set_page_config(
    page_title="无人机地面站系统",
    page_icon="🛸",
    layout="wide"
)

# ============================ 侧边栏 ============================

st.sidebar.markdown("# 🚁 导航")
page = st.sidebar.radio("功能页面", ["🗺️ 航线规划", "💓 飞行监控"])

st.sidebar.markdown("---")
st.sidebar.markdown("# 📐 坐标系设置")

coord_sys = st.sidebar.selectbox(
    "输入坐标系",
    ["WGS-84", "GCJ-02(高德/百度)"],
    index=0 if st.session_state.coord_system == "WGS-84" else 1
)
st.session_state.coord_system = coord_sys.split("(")[0]

st.sidebar.markdown("---")
st.sidebar.markdown("## 📖 操作说明")
st.sidebar.markdown("- 📍 **设置A/B点**: 输入坐标后点击按钮")
st.sidebar.markdown("- 🚧 **添加障碍物**: 展开面板添加")
st.sidebar.markdown("- 🗺️ **简图视图**: 显示相对位置")
st.sidebar.markdown("- 📊 **表格视图**: 显示详细坐标")
st.sidebar.markdown("- 💓 **飞行监控**: 实时心跳监测")
st.sidebar.markdown("")
st.sidebar.markdown("### 📡 校园坐标参考")
st.sidebar.markdown("- 教学楼: 32.2328, 118.7485")
st.sidebar.markdown("- 图书馆: 32.2335, 118.7492")
st.sidebar.markdown("- 实验楼: 32.2330, 118.7500")
st.sidebar.markdown("- 食堂: 32.2325, 118.7495")
st.sidebar.markdown("- 体育馆: 32.2318, 118.7482")

# ============================ 航线规划页面 ============================

if page == "🗺️ 航线规划":
    st.title("🗺️ 航线规划")
    st.markdown("无人机航线规划系统 | 支持 WGS-84 / GCJ-02 坐标系转换")
    
    col1, col2 = st.columns([1, 1.2])
    
    with col1:
        st.markdown("### 🎮 控制面板")
        
        # 起点A
        st.markdown("#### 📍 起点A")
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
        st.markdown("#### 🎯 终点B")
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
        st.markdown("#### ✈️ 飞行参数")
        st.session_state.flight_height = st.number_input(
            "飞行高度 (m)", 
            value=st.session_state.flight_height, 
            step=5.0,
            help="无人机飞行的高度"
        )
        
        # 障碍物管理
        st.markdown("#### 🚧 障碍物管理")
        with st.expander("➕ 添加新障碍物", expanded=False):
            obs_name = st.text_input("障碍物名称", "新障碍物")
            col_o1, col_o2 = st.columns(2)
            with col_o1:
                obs_lat = st.number_input("纬度", value=32.2330, format="%.6f", key="obs_lat")
            with col_o2:
                obs_lng = st.number_input("经度", value=118.7495, format="%.6f", key="obs_lng")
            obs_radius = st.number_input("半径 (m)", value=25, step=5, key="obs_radius")
            if st.button("✅ 确认添加", key="add_obs"):
                st.session_state.obstacles.append({
                    "lat": obs_lat,
                    "lng": obs_lng,
                    "radius": obs_radius,
                    "name": obs_name
                })
                st.success(f"✅ 已添加障碍物: {obs_name}")
                st.rerun()
    
    with col2:
        st.markdown("### 📊 系统状态")
        
        # 状态显示
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
            st.success(f"📏 **航线直线距离**: {distance:.1f} 米")
        
        # 障碍物列表
        if st.session_state.obstacles:
            st.markdown("**🚧 障碍物列表**")
            for i, obs in enumerate(st.session_state.obstacles):
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.write(f"{i+1}. {obs['name']} (半径: {obs['radius']}m)")
                    st.caption(f"   📍 {obs['lat']:.6f}, {obs['lng']:.6f}")
                with col_b:
                    if st.button("🗑️", key=f"del_{i}"):
                        st.session_state.obstacles.pop(i)
                        st.rerun()
    
    # 地图显示区域
    st.markdown("### 🗺️ 地图视图")
    
    # 创建选项卡
    tab1, tab2, tab3 = st.tabs(["🗺️ 简图视图", "📊 表格视图", "📐 坐标转换详情"])
    
    with tab1:
        display_ascii_map()
        
        # 显示航线信息
        if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
            distance = calculate_distance(
                st.session_state.point_A["lat"], st.session_state.point_A["lng"],
                st.session_state.point_B["lat"], st.session_state.point_B["lng"]
            )
            st.info(f"✈️ **航线信息**: 起点A → 终点B | 直线距离 {distance:.1f} 米 | 飞行高度 {st.session_state.flight_height} 米")
    
    with tab2:
        display_coordinate_table()
    
    with tab3:
        st.markdown("### 坐标系转换说明")
        st.markdown("""
        #### WGS-84 与 GCJ-02 坐标系转换
        
        | 坐标系 | 说明 | 使用场景 |
        |--------|------|----------|
        | **WGS-84** | 国际标准坐标系 | GPS设备、Google Earth |
        | **GCJ-02** | 火星坐标系 | 高德地图、百度地图(BD-09需二次转换) |
        
        #### 转换示例
        """)
        
        # 显示转换示例
        test_lat, test_lng = 32.2322, 118.749
        gcj_lng, gcj_lat = wgs84_to_gcj02(test_lng, test_lat)
        st.markdown(f"- WGS-84 → GCJ-02: ({test_lat:.6f}, {test_lng:.6f}) → ({gcj_lat:.6f}, {gcj_lng:.6f})")
        
        st.markdown("""
        #### 注意事项
        - 在中国境内，WGS-84 和 GCJ-02 之间存在偏移
        - 高德地图使用 GCJ-02 坐标系
        - 本系统会自动进行坐标转换
        """)

# ============================ 飞行监控页面 ============================

else:
    st.title("🛸 无人机心跳监测系统")
    st.markdown("模拟无人机每秒发送心跳包，地面站实时监测，3秒未收到自动报警")
    
    # 自动刷新
    if st.session_state.running:
        st.markdown('<meta http-equiv="refresh" content="1">', unsafe_allow_html=True)
    
    # 控制按钮
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

# ============================ 底部信息 ============================

st.markdown("---")
st.markdown(
    "© 2024 无人机地面站系统 | "
    "支持 WGS-84 / GCJ-02 坐标系转换 | "
    "实时心跳监测 | "
    "简图显示相对位置"
)
