import streamlit as st
from streamlit_folium import st_folium
import folium
import math
import random
import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
from datetime import datetime

# -------------------------- 页面全局配置 --------------------------
st.set_page_config(
    page_title="无人机智能化应用",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------- 会话状态初始化（关键：跨页面数据共享） --------------------------
if "current_page" not in st.session_state:
    st.session_state.current_page = "航线规划"
if "a_point" not in st.session_state:
    st.session_state.a_point = {"lat": 32.23, "lon": 118.75, "set": False}
if "b_point" not in st.session_state:
    st.session_state.b_point = {"lat": 32.24, "lon": 118.76, "set": False}
if "flight_data" not in st.session_state:
    # 模拟无人机飞行监控数据（可对接真实无人机API）
    st.session_state.flight_data = pd.DataFrame({
        "时间": [datetime.now().strftime("%H:%M:%S")],
        "纬度": [32.235],
        "经度": [118.755],
        "高度(m)": [50.0],
        "速度(m/s)": [3.2],
        "电量(%)": [85],
        "状态": ["正常飞行"]
    })

# -------------------------- 侧边栏（导航+坐标系+状态） --------------------------
with st.sidebar:
    st.header("🚁 导航")
    st.subheader("功能页面")
    
    # 页面切换按钮（核心：保留飞行监控）
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📖 航线规划", type="primary" if st.session_state.current_page == "航线规划" else "secondary", use_container_width=True):
            st.session_state.current_page = "航线规划"
            st.rerun()
    with col2:
        if st.button("📡 飞行监控", type="primary" if st.session_state.current_page == "飞行监控" else "secondary", use_container_width=True):
            st.session_state.current_page = "飞行监控"
            st.rerun()
    
    st.divider()
    
    # 坐标系设置（双页面共享）
    st.subheader("⚙️ 坐标系设置")
    st.write("输入坐标系")
    coord_system = st.radio(
        "",
        ["WGS-84", "GCJ-02(高德/百度)"],
        index=1,
        label_visibility="collapsed"
    )
    
    st.divider()
    
    # 系统状态（双页面共享）
    st.subheader("✅ 系统状态")
    st.write(f"A点状态: {'已设置' if st.session_state.a_point['set'] else '未设置'}")
    st.write(f"B点状态: {'已设置' if st.session_state.b_point['set'] else '未设置'}")
    if st.session_state.current_page == "飞行监控":
        st.write(f"无人机状态: {st.session_state.flight_data.iloc[-1]['状态']}")
        st.write(f"当前电量: {st.session_state.flight_data.iloc[-1]['电量(%)']}%")

# -------------------------- 页面1：航线规划（完全保留你当前的功能） --------------------------
if st.session_state.current_page == "航线规划":
    # 分三栏布局：地图主体 + 右侧控制面板
    col_map, col_ctrl = st.columns([3, 1])

    # 右侧控制面板
    with col_ctrl:
        st.header("⚙️ 控制面板")
        
        # 起点A设置
        st.subheader("📍 起点A")
        a_lat = st.number_input("纬度", value=st.session_state.a_point["lat"], min_value=-90.0, max_value=90.0, step=0.01, key="a_lat")
        a_lon = st.number_input("经度", value=st.session_state.a_point["lon"], min_value=-180.0, max_value=180.0, step=0.01, key="a_lon")
        set_a = st.checkbox("✅ 设置A点", value=st.session_state.a_point["set"], key="set_a")
        
        # 终点B设置
        st.subheader("📍 终点B")
        b_lat = st.number_input("纬度", value=st.session_state.b_point["lat"], min_value=-90.0, max_value=90.0, step=0.01, key="b_lat")
        b_lon = st.number_input("经度", value=st.session_state.b_point["lon"], min_value=-180.0, max_value=180.0, step=0.01, key="b_lon")
        set_b = st.checkbox("✅ 设置B点", value=st.session_state.b_point["set"], key="set_b")
        
        # 更新A/B点状态
        if set_a:
            st.session_state.a_point = {"lat": a_lat, "lon": a_lon, "set": True}
        else:
            st.session_state.a_point["set"] = False
        if set_b:
            st.session_state.b_point = {"lat": b_lat, "lon": b_lon, "set": True}
        else:
            st.session_state.b_point["set"] = False

    # 中间3D地图区域
    with col_map:
        st.header("🗺️ 3D校园地图")
        
        # 底图配置
        if coord_system == "GCJ-02(高德/百度)":
            tile_url = "https://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"
            tile_attr = "&copy; 高德地图"
            center_lat, center_lon = st.session_state.a_point["lat"], st.session_state.a_point["lon"]
        else:
            tile_url = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            tile_attr = "&copy; OpenStreetMap contributors"
            center_lat, center_lon = st.session_state.a_point["lat"], st.session_state.a_point["lon"]
        
        # 地图初始化
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=17,
            tiles=tile_url,
            attr=tile_attr,
            control_scale=True,
            prefer_canvas=True
        )
        
        # 标记A/B点+航线
        if st.session_state.a_point["set"]:
            folium.Marker(
                location=[st.session_state.a_point["lat"], st.session_state.a_point["lon"]],
                popup="起点A",
                icon=folium.Icon(color="red", icon="map-marker")
            ).add_to(m)
        if st.session_state.b_point["set"]:
            folium.Marker(
                location=[st.session_state.b_point["lat"], st.session_state.b_point["lon"]],
                popup="终点B",
                icon=folium.Icon(color="blue", icon="map-marker")
            ).add_to(m)
            # 绘制A-B航线
            if st.session_state.a_point["set"]:
                folium.PolyLine(
                    locations=[
                        [st.session_state.a_point["lat"], st.session_state.a_point["lon"]],
                        [st.session_state.b_point["lat"], st.session_state.b_point["lon"]]
                    ],
                    color="green",
                    weight=3,
                    opacity=0.8
                ).add_to(m)
        
        # 渲染地图
        st_folium(m, width="100%", height=600, key="route_map")

# -------------------------- 页面2：飞行监控（完整保留+功能增强） --------------------------
elif st.session_state.current_page == "飞行监控":
    st.header("📡 无人机飞行监控")
    
    # 分栏布局：地图 + 实时数据面板
    col_map, col_data = st.columns([2, 1])
    
    # 左侧：实时飞行轨迹地图
    with col_map:
        st.subheader("🗺️ 实时飞行轨迹")
        
        # 底图配置（和航线规划页一致）
        if coord_system == "GCJ-02(高德/百度)":
            tile_url = "https://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"
            tile_attr = "&copy; 高德地图"
        else:
            tile_url = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            tile_attr = "&copy; OpenStreetMap contributors"
        
        # 以无人机最新位置为中心
        latest = st.session_state.flight_data.iloc[-1]
        m = folium.Map(
            location=[latest["纬度"], latest["经度"]],
            zoom_start=17,
            tiles=tile_url,
            attr=tile_attr,
            control_scale=True
        )
        
        # 绘制历史飞行轨迹
        folium.PolyLine(
            locations=st.session_state.flight_data[["纬度", "经度"]].values.tolist(),
            color="red",
            weight=2,
            opacity=0.7
        ).add_to(m)
        
        # 标记当前无人机位置
        folium.Marker(
            location=[latest["纬度"], latest["经度"]],
            popup=f"当前位置\n高度: {latest['高度(m)']}m\n速度: {latest['速度(m/s)']}m/s",
            icon=folium.Icon(color="green", icon="plane")
        ).add_to(m)
        
        # 渲染地图
        st_folium(m, width="100%", height=500, key="flight_map")
        
        # 模拟数据更新按钮（对接真实无人机时可删除）
        if st.button("🔄 更新飞行数据", use_container_width=True):
            # 模拟无人机位置移动、电量下降
            new_row = {
                "时间": datetime.now().strftime("%H:%M:%S"),
                "纬度": latest["纬度"] + 0.0001,
                "经度": latest["经度"] + 0.0001,
                "高度(m)": round(latest["高度(m)"] + 0.5, 1),
                "速度(m/s)": round(latest["速度(m/s)"] + 0.1, 1),
                "电量(%)": max(latest["电量(%)"] - 1, 0),
                "状态": "正常飞行" if latest["电量(%)"] > 20 else "低电量告警"
            }
            st.session_state.flight_data = pd.concat([st.session_state.flight_data, pd.DataFrame([new_row])], ignore_index=True)
            st.rerun()
    
    # 右侧：实时数据面板
    with col_data:
        st.subheader("📊 实时参数")
        # 显示最新数据
        latest = st.session_state.flight_data.iloc[-1]
        
        # 关键指标卡片
        col1, col2 = st.columns(2)
        with col1:
            st.metric(label="📏 高度(m)", value=latest["高度(m)"])
            st.metric(label="🔋 电量(%)", value=latest["电量(%)"], delta=f"-{1}%")
        with col2:
            st.metric(label="⚡ 速度(m/s)", value=latest["速度(m/s)"])
            st.metric(label="📍 状态", value=latest["状态"])
        
        st.divider()
        
        # 详细坐标信息
        st.subheader("📍 当前位置")
        st.write(f"纬度: {latest['纬度']:.4f}")
        st.write(f"经度: {latest['经度']:.4f}")
        st.write(f"坐标系: {coord_system}")
        
        st.divider()
        
        # 历史数据表格
        st.subheader("📋 飞行历史")
        st.dataframe(st.session_state.flight_data, use_container_width=True, hide_index=True)

# -------------------------- 依赖说明（Streamlit Cloud自动安装） --------------------------
# requirements.txt 内容：
# streamlit==1.35.0
# folium==0.16.0
# streamlit-folium==0.17.0
# pandas==2.2.2
 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
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
