import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
from datetime import datetime
import json
import os
import math
import random
from folium import plugins
from shapely.geometry import Polygon, Point, LineString

# -------------------------- 页面全局配置 --------------------------
st.set_page_config(
    page_title="无人机智能化应用",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------- 会话状态初始化 --------------------------
if "current_page" not in st.session_state:
    st.session_state.current_page = "航线规划"
if "a_point" not in st.session_state:
    st.session_state.a_point = {"lat": 32.2323, "lon": 118.749, "set": False}
if "b_point" not in st.session_state:
    st.session_state.b_point = {"lat": 32.2344, "lon": 118.749, "set": False}
if "flight_data" not in st.session_state:
    st.session_state.flight_data = pd.DataFrame({
        "时间": [datetime.now().strftime("%H:%M:%S")],
        "纬度": [32.23335],
        "经度": [118.749],
        "高度(m)": [50.0],
        "速度(m/s)": [3.2],
        "电量(%)": [85],
        "状态": ["正常飞行"]
    })
if "obstacles" not in st.session_state:
    st.session_state.obstacles = []  # 存储障碍物: [{"polygon": [[lat,lon],...], "height": 10}, ...]
if "flight_height" not in st.session_state:
    st.session_state.flight_height = 10
if "safety_radius" not in st.session_state:
    st.session_state.safety_radius = 5
if "selected_obstacle_index" not in st.session_state:
    st.session_state.selected_obstacle_index = None
if "bypass_strategy" not in st.session_state:
    st.session_state.bypass_strategy = "最佳航线"
if "planned_route" not in st.session_state:
    st.session_state.planned_route = []  # 存储规划好的航线 [[lat,lon], ...]

# -------------------------- 配置文件路径 --------------------------
CONFIG_FILE = "obstacle_config.json"

# -------------------------- 障碍物持久化函数 --------------------------
def save_obstacles_to_file():
    """保存障碍物配置到文件（包含高度信息）"""
    config = {
        "obstacles": st.session_state.obstacles,
        "save_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "version": "v12.3 障碍物高度持久化版"
    }
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    st.success(f"✅ 已保存 {len(st.session_state.obstacles)} 个障碍物（含高度）到 {CONFIG_FILE}")

def load_obstacles_from_file():
    """从文件加载障碍物配置"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        st.session_state.obstacles = config.get("obstacles", [])
        st.success(f"✅ 已加载 {len(st.session_state.obstacles)} 个障碍物，保存时间: {config.get('save_time', '未知')}")
        st.rerun()
    else:
        st.warning("⚠️ 配置文件不存在，请先保存")

def clear_all_obstacles():
    """清除所有障碍物"""
    st.session_state.obstacles = []
    st.session_state.selected_obstacle_index = None
    st.success("✅ 已清除所有障碍物")
    st.rerun()

# -------------------------- 障碍物高度设置 --------------------------
def set_obstacle_height(index, height):
    """设置指定障碍物的高度"""
    if 0 <= index < len(st.session_state.obstacles):
        st.session_state.obstacles[index]["height"] = height
        st.success(f"✅ 障碍物 {index+1} 高度已设置为 {height} 米")
        st.rerun()

# -------------------------- 航线规划核心算法 --------------------------
def calculate_route_with_obstacles(A, B, flight_height, safety_radius, obstacles, bypass_strategy):
    """
    根据障碍物规划航线
    返回: 航线点列表 [[lat,lon], ...]
    """
    if not A["set"] or not B["set"]:
        return []
    
    start = (A["lat"], A["lon"])
    end = (B["lat"], B["lon"])
    
    # 如果没有障碍物，直接返回直线
    if not obstacles:
        return [start, end]
    
    # 检查障碍物是否需要绕行
    obstacles_to_bypass = []
    for obs in obstacles:
        polygon = Polygon(obs["polygon"])
        obs_height = obs.get("height", 0)
        
        # 判断航线是否与障碍物相交
        line = LineString([start, end])
        if line.intersects(polygon):
            if flight_height > obs_height:
                # 飞跃，不需要绕行
                continue
            else:
                # 需要绕行
                obstacles_to_bypass.append({
                    "polygon": polygon,
                    "height": obs_height,
                    "center": polygon.centroid
                })
    
    # 如果没有需要绕行的障碍物，返回直线
    if not obstacles_to_bypass:
        return [start, end]
    
    # 根据策略计算绕行点
    if bypass_strategy == "向左绕行":
        return calculate_left_bypass(start, end, obstacles_to_bypass, safety_radius)
    elif bypass_strategy == "向右绕行":
        return calculate_right_bypass(start, end, obstacles_to_bypass, safety_radius)
    else:  # 最佳航线
        return calculate_optimal_bypass(start, end, obstacles_to_bypass, safety_radius)

def calculate_left_bypass(start, end, obstacles, safety_radius):
    """向左绕行策略：从障碍物左侧绕过"""
    waypoints = [start]
    current = start
    
    # 简化算法：对每个障碍物，计算左侧绕行点
    for obs in obstacles:
        # 获取障碍物的最小包围矩形
        minx, miny, maxx, maxy = obs["polygon"].bounds
        center_lat = (miny + maxy) / 2
        center_lon = (minx + maxx) / 2
        
        # 计算左侧绕行点（垂直于航线方向）
        dx = end[1] - start[1]
        dy = end[0] - start[0]
        length = math.sqrt(dx*dx + dy*dy)
        if length > 0:
            perp_x = -dy / length  # 垂直方向（左）
            perp_y = dx / length
        else:
            perp_x, perp_y = 0, 1
        
        # 绕行点：障碍物中心 + 垂直偏移 * (安全半径 + 障碍物半宽)
        half_width = (maxx - minx) / 2
        offset = safety_radius + half_width
        bypass_lon = center_lon + perp_x * offset * 0.0001  # 转换为经纬度近似
        bypass_lat = center_lat + perp_y * offset * 0.0001
        
        waypoints.append((bypass_lat, bypass_lon))
        current = (bypass_lat, bypass_lon)
    
    waypoints.append(end)
    return waypoints

def calculate_right_bypass(start, end, obstacles, safety_radius):
    """向右绕行策略：从障碍物右侧绕过"""
    waypoints = [start]
    current = start
    
    for obs in obstacles:
        minx, miny, maxx, maxy = obs["polygon"].bounds
        center_lat = (miny + maxy) / 2
        center_lon = (minx + maxx) / 2
        
        dx = end[1] - start[1]
        dy = end[0] - start[0]
        length = math.sqrt(dx*dx + dy*dy)
        if length > 0:
            perp_x = dy / length   # 垂直方向（右）
            perp_y = -dx / length
        else:
            perp_x, perp_y = 0, 1
        
        half_width = (maxx - minx) / 2
        offset = safety_radius + half_width
        bypass_lon = center_lon + perp_x * offset * 0.0001
        bypass_lat = center_lat + perp_y * offset * 0.0001
        
        waypoints.append((bypass_lat, bypass_lon))
        current = (bypass_lat, bypass_lon)
    
    waypoints.append(end)
    return waypoints

def calculate_optimal_bypass(start, end, obstacles, safety_radius):
    """最佳航线策略：选择最短路径"""
    left_route = calculate_left_bypass(start, end, obstacles, safety_radius)
    right_route = calculate_right_bypass(start, end, obstacles, safety_radius)
    
    # 计算两条路线的总长度，选择较短的
    def route_length(route):
        length = 0
        for i in range(len(route)-1):
            dx = route[i+1][1] - route[i][1]
            dy = route[i+1][0] - route[i][0]
            length += math.sqrt(dx*dx + dy*dy)
        return length
    
    if route_length(left_route) <= route_length(right_route):
        return left_route
    else:
        return right_route

# -------------------------- 心跳包模拟 --------------------------
def simulate_heartbeat():
    """模拟无人机心跳包，更新飞行数据"""
    latest = st.session_state.flight_data.iloc[-1]
    
    # 如果有规划的航线，沿着航线移动
    if st.session_state.planned_route and len(st.session_state.planned_route) > 1:
        # 找到当前位置在航线上的最近点，向下一目标移动
        current_pos = (latest["纬度"], latest["经度"])
        target_idx = 1
        for i, point in enumerate(st.session_state.planned_route):
            dist = math.hypot(point[0] - current_pos[0], point[1] - current_pos[1])
            if dist < 0.0002:  # 到达该航点
                target_idx = min(i+1, len(st.session_state.planned_route)-1)
        
        target = st.session_state.planned_route[target_idx]
        # 向目标移动
        dx = target[0] - current_pos[0]
        dy = target[1] - current_pos[1]
        dist = math.hypot(dx, dy)
        if dist > 0:
            step = 0.0001  # 移动步长
            ratio = min(1.0, step / dist)
            new_lat = current_pos[0] + dx * ratio
            new_lon = current_pos[1] + dy * ratio
        else:
            new_lat, new_lon = current_pos
    else:
        # 默认模拟移动
        new_lat = latest["纬度"] + random.uniform(-0.0002, 0.0002)
        new_lon = latest["经度"] + random.uniform(-0.0002, 0.0002)
    
    new_height = latest["高度(m)"] + random.uniform(-1, 1)
    new_height = max(0, min(200, new_height))
    
    new_row = {
        "时间": datetime.now().strftime("%H:%M:%S"),
        "纬度": round(new_lat, 6),
        "经度": round(new_lon, 6),
        "高度(m)": round(new_height, 1),
        "速度(m/s)": round(latest["速度(m/s)"] + random.uniform(-0.5, 0.5), 1),
        "电量(%)": max(latest["电量(%)"] - random.uniform(0, 2), 0),
        "状态": "正常飞行" if latest["电量(%)"] > 20 else "低电量告警"
    }
    st.session_state.flight_data = pd.concat([st.session_state.flight_data, pd.DataFrame([new_row])], ignore_index=True)

# -------------------------- 侧边栏 --------------------------
with st.sidebar:
    st.header("🚁 导航")
    st.subheader("功能页面")
    
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
    
    st.subheader("⚙️ 坐标系设置")
    coord_system = st.radio(
        "",
        ["WGS-84", "GCJ-02(高德/百度)"],
        index=1,
        label_visibility="collapsed"
    )
    
    st.divider()
    
    st.subheader("✅ 系统状态")
    st.write(f"A点状态: {'已设置' if st.session_state.a_point['set'] else '未设置'}")
    st.write(f"B点状态: {'已设置' if st.session_state.b_point['set'] else '未设置'}")
    if st.session_state.current_page == "飞行监控":
        st.write(f"无人机状态: {st.session_state.flight_data.iloc[-1]['状态']}")
        st.write(f"当前电量: {st.session_state.flight_data.iloc[-1]['电量(%)']:.1f}%")

# -------------------------- 页面1：航线规划 --------------------------
if st.session_state.current_page == "航线规划":
    col_map, col_ctrl = st.columns([3, 1])

    with col_ctrl:
        st.header("⚙️ 控制面板")
        
        st.subheader("📍 起点A")
        a_lat = st.number_input("纬度", value=st.session_state.a_point["lat"], min_value=-90.0, max_value=90.0, step=0.0001, key="a_lat", format="%.4f")
        a_lon = st.number_input("经度", value=st.session_state.a_point["lon"], min_value=-180.0, max_value=180.0, step=0.0001, key="a_lon", format="%.4f")
        set_a = st.checkbox("✅ 设置A点", value=st.session_state.a_point["set"], key="set_a")
        
        st.subheader("📍 终点B")
        b_lat = st.number_input("纬度", value=st.session_state.b_point["lat"], min_value=-90.0, max_value=90.0, step=0.0001, key="b_lat", format="%.4f")
        b_lon = st.number_input("经度", value=st.session_state.b_point["lon"], min_value=-180.0, max_value=180.0, step=0.0001, key="b_lon", format="%.4f")
        set_b = st.checkbox("✅ 设置B点", value=st.session_state.b_point["set"], key="set_b")
        
        st.subheader("✈️ 飞行参数")
        st.session_state.flight_height = st.number_input("设定飞行高度(m)", value=st.session_state.flight_height, min_value=5, max_value=200, step=5)
        st.session_state.safety_radius = st.number_input("无人机安全半径(m)", value=st.session_state.safety_radius, min_value=1, max_value=20, step=1)
        
        st.subheader("🔄 绕行策略")
        st.session_state.bypass_strategy = st.selectbox(
            "选择绕行方式",
            ["向左绕行", "向右绕行", "最佳航线"],
            index=["向左绕行", "向右绕行", "最佳航线"].index(st.session_state.bypass_strategy)
        )
        
        # 航线规划按钮
        if st.button("🚀 规划航线", type="primary", use_container_width=True):
            if st.session_state.a_point["set"] and st.session_state.b_point["set"]:
                st.session_state.planned_route = calculate_route_with_obstacles(
                    st.session_state.a_point,
                    st.session_state.b_point,
                    st.session_state.flight_height,
                    st.session_state.safety_radius,
                    st.session_state.obstacles,
                    st.session_state.bypass_strategy
                )
                if st.session_state.planned_route:
                    st.success(f"✅ 航线规划完成！共 {len(st.session_state.planned_route)} 个航点")
                else:
                    st.warning("⚠️ 航线规划失败，请检查起终点设置")
            else:
                st.warning("⚠️ 请先设置起点A和终点B")
        
        if set_a:
            st.session_state.a_point = {"lat": a_lat, "lon": a_lon, "set": True}
        else:
            st.session_state.a_point["set"] = False
        if set_b:
            st.session_state.b_point = {"lat": b_lat, "lon": b_lon, "set": True}
        else:
            st.session_state.b_point["set"] = False
        
        st.divider()
        
        st.subheader("🚧 障碍物管理")
        
        # 障碍物高度设置
        if st.session_state.obstacles:
            st.write("**设置障碍物高度:**")
            obs_options = [f"障碍物 {i+1} (当前高度: {obs.get('height', 0)}m)" for i, obs in enumerate(st.session_state.obstacles)]
            selected_idx = st.selectbox("选择障碍物", range(len(obs_options)), format_func=lambda x: obs_options[x], key="obs_select")
            obs_height = st.number_input("设置高度(m)", value=st.session_state.obstacles[selected_idx].get("height", 10), min_value=0, max_value=100, step=5)
            if st.button("✏️ 设置高度", use_container_width=True):
                set_obstacle_height(selected_idx, obs_height)
        
        st.divider()
        
        st.subheader("💾 持久化存储")
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("💾 保存到文件", use_container_width=True):
                save_obstacles_to_file()
        with col_btn2:
            if st.button("📂 从文件加载", use_container_width=True):
                load_obstacles_from_file()
        
        col_btn3, col_btn4 = st.columns(2)
        with col_btn3:
            if st.button("🗑️ 清除全部", use_container_width=True):
                clear_all_obstacles()
        with col_btn4:
            st.download_button(
                label="📥 下载配置",
                data=json.dumps({"obstacles": st.session_state.obstacles, "version": "v12.3"}, ensure_ascii=False, indent=2),
                file_name="obstacle_config.json",
                mime="application/json",
                use_container_width=True
            )
        
        if st.session_state.obstacles:
            st.info(f"📊 当前共 {len(st.session_state.obstacles)} 个障碍物")

    with col_map:
        st.header("🗺️ 地图绘制 (多边形圈选障碍物)")
        
        if coord_system == "GCJ-02(高德/百度)":
            tile_url = "https://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"
            tile_attr = "&copy; 高德地图"
        else:
            tile_url = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            tile_attr = "&copy; OpenStreetMap contributors"
        
        center_lat = st.session_state.a_point["lat"] if st.session_state.a_point["set"] else 32.2323
        center_lon = st.session_state.a_point["lon"] if st.session_state.a_point["set"] else 118.749
        
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=18,
            tiles=tile_url,
            attr=tile_attr,
            control_scale=True
        )
        
        # 添加绘制控件（只允许多边形）
        draw = plugins.Draw(
            export=True,
            position='topleft',
            draw_options={
                'polygon': {'allowIntersection': False, 'showArea': True, 'shapeOptions': {'color': '#ff0000'}},
                'polyline': False,
                'rectangle': False,
                'circle': False,
                'marker': False,
                'circlemarker': False
            },
            edit_options={'edit': True, 'remove': True}
        )
        draw.add_to(m)
        
        # 绘制已保存的障碍物（带高度显示）
        for i, obstacle in enumerate(st.session_state.obstacles):
            polygon_coords = obstacle["polygon"]
            height = obstacle.get("height", 0)
            folium.Polygon(
                locations=polygon_coords,
                color="red",
                weight=2,
                fill=True,
                fill_color="red",
                fill_opacity=0.3,
                popup=f"障碍物 {i+1} | 高度: {height}m"
            ).add_to(m)
            # 添加中心点标记
            center_lat = sum(p[0] for p in polygon_coords) / len(polygon_coords)
            center_lon = sum(p[1] for p in polygon_coords) / len(polygon_coords)
            folium.Marker(
                location=[center_lat, center_lon],
                icon=folium.DivIcon(html=f'<div style="font-size: 10px; color: red;">{height}m</div>'),
                popup=f"障碍物 {i+1} 中心"
            ).add_to(m)
        
        # 绘制A、B点
        if st.session_state.a_point["set"]:
            folium.Marker(
                location=[st.session_state.a_point["lat"], st.session_state.a_point["lon"]],
                popup=f"起点A (高: {st.session_state.flight_height}m)",
                icon=folium.Icon(color="green", icon="play", prefix='fa')
            ).add_to(m)
        if st.session_state.b_point["set"]:
            folium.Marker(
                location=[st.session_state.b_point["lat"], st.session_state.b_point["lon"]],
                popup="终点B",
                icon=folium.Icon(color="blue", icon="flag-checkered", prefix='fa')
            ).add_to(m)
        
        # 绘制规划的航线
        if st.session_state.planned_route and len(st.session_state.planned_route) >= 2:
            folium.PolyLine(
                locations=st.session_state.planned_route,
                color="green",
                weight=4,
                opacity=0.8,
                popup=f"规划航线 | 策略: {st.session_state.bypass_strategy}"
            ).add_to(m)
            # 添加航点标记
            for i, point in enumerate(st.session_state.planned_route):
                folium.CircleMarker(
                    location=point,
                    radius=3,
                    color="green",
                    fill=True,
                    popup=f"航点 {i+1}"
                ).add_to(m)
        
        # 渲染地图并获取绘制的数据
        output = st_folium(m, width="100%", height=650, key="route_map")
        
        # 处理新绘制的多边形（添加障碍物）
        if output and output.get("last_active_drawing"):
            drawing = output["last_active_drawing"]
            if drawing.get("geometry", {}).get("type") == "Polygon":
                coordinates = drawing["geometry"]["coordinates"][0]
                # 转换坐标格式 [[lng, lat], ...] -> [[lat, lng], ...]
                polygon_coords = [[coord[1], coord[0]] for coord in coordinates]
                # 添加新障碍物，默认高度10米
                new_obstacle = {
                    "polygon": polygon_coords,
                    "height": 10
                }
                st.session_state.obstacles.append(new_obstacle)
                st.success(f"✅ 已添加障碍物 {len(st.session_state.obstacles)}，默认高度10米，请在左侧设置高度")
                st.rerun()

# -------------------------- 页面2：飞行监控 --------------------------
elif st.session_state.current_page == "飞行监控":
    st.header("📡 无人机飞行监控")
    
    # 自动更新心跳（模拟）
    if st.button("🔄 模拟心跳包更新", use_container_width=True):
        simulate_heartbeat()
        st.rerun()
    
    # 自动刷新选项
    auto_refresh = st.checkbox("自动刷新数据（每3秒）", value=False)
    if auto_refresh:
        import time
        time.sleep(3)
        simulate_heartbeat()
        st.rerun()
    
    col_map, col_data = st.columns([2, 1])
    
    with col_map:
        st.subheader("🗺️ 实时飞行轨迹")
        
        if coord_system == "GCJ-02(高德/百度)":
            tile_url = "https://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"
            tile_attr = "&copy; 高德地图"
        else:
            tile_url = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            tile_attr = "&copy; OpenStreetMap contributors"
        
        latest = st.session_state.flight_data.iloc[-1]
        m = folium.Map(
            location=[latest["纬度"], latest["经度"]],
            zoom_start=18,
            tiles=tile_url,
            attr=tile_attr,
            control_scale=True
        )
        
        # 绘制障碍物
        for i, obstacle in enumerate(st.session_state.obstacles):
            folium.Polygon(
                locations=obstacle["polygon"],
                color="red",
                weight=2,
                fill=True,
                fill_color="red",
                fill_opacity=0.3,
                popup=f"障碍物 {i+1} | 高度: {obstacle.get('height', 0)}m"
            ).add_to(m)
        
        # 绘制历史飞行轨迹
        if len(st.session_state.flight_data) > 1:
            folium.PolyLine(
                locations=st.session_state.flight_data[["纬度", "经度"]].values.tolist(),
                color="blue",
                weight=2,
                opacity=0.7,
                popup="飞行轨迹"
            ).add_to(m)
        
        # 绘制规划的航线（如果有）
        if st.session_state.planned_route and len(st.session_state.planned_route) >= 2:
            folium.PolyLine(
                locations=st.session_state.planned_route,
                color="green",
                weight=3,
                opacity=0.5,
                dash_array='5, 5',
                popup="规划航线"
            ).add_to(m)
        
        folium.Marker(
            location=[latest["纬度"], latest["经度"]],
            popup=f"当前位置\n高度: {latest['高度(m)']}m\n速度: {latest['速度(m/s)']}m/s",
            icon=folium.Icon(color="red", icon="plane", prefix='fa')
        ).add_to(m)
        
        st_folium(m, width="100%", height=550, key="flight_map")
    
    with col_data:
        st.subheader("📊 实时参数")
        latest = st.session_state.flight_data.iloc[-1]
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric(label="📏 高度(m)", value=f"{latest['高度(m)']:.1f}")
            st.metric(label="🔋 电量(%)", value=f"{latest['电量(%)']:.1f}")
        with col2:
            st.metric(label="⚡ 速度(m/s)", value=f"{latest['速度(m/s)']:.1f}")
            st.metric(label="📍 状态", value=latest['状态'])
        
        st.divider()
        
        st.subheader("📍 当前位置")
        st.write(f"纬度: {latest['纬度']:.6f}")
        st.write(f"经度: {latest['经度']:.6f}")
        st.write(f"坐标系: {coord_system}")
        
        st.divider()
        
        # 航线信息显示
        st.subheader("✈️ 航线信息")
        if st.session_state.planned_route:
            st.write(f"航点数量: {len(st.session_state.planned_route)}")
            st.write(f"绕行策略: {st.session_state.bypass_strategy}")
        else:
            st.info("暂无规划航线，请先返回航线规划页面设置")
        
        if st.session_state.obstacles:
            st.divider()
            st.subheader("🚧 障碍物列表")
            for i, obs in enumerate(st.session_state.obstacles):
                st.write(f"障碍物 {i+1}: {len(obs['polygon'])} 个顶点 | 高度: {obs.get('height', 0)}m")
        
        st.divider()
        st.subheader("📋 飞行历史")
        st.dataframe(st.session_state.flight_data.tail(10), use_container_width=True, hide_index=True)
