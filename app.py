import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
from datetime import datetime
import json
import os
import math
import numpy as np
from folium import plugins
from shapely.geometry import Polygon, Point, LineString
from shapely.ops import nearest_points

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
    st.session_state.obstacles = []  # 存储障碍物 {"coords": [[lat,lon],...], "height": 20}
if "flight_height" not in st.session_state:
    st.session_state.flight_height = 10
if "safe_radius" not in st.session_state:
    st.session_state.safe_radius = 5
if "selected_obstacle_index" not in st.session_state:
    st.session_state.selected_obstacle_index = None
if "planned_route" not in st.session_state:
    st.session_state.planned_route = None

# -------------------------- 配置文件路径 --------------------------
CONFIG_FILE = "obstacle_config.json"

# -------------------------- 坐标转换函数 --------------------------
def wgs84_to_gcj02(lat, lon):
    """WGS84转GCJ02（简化版火星坐标系）"""
    if lat < 29.0 or lat > 42.0 or lon < 109.0 or lon > 124.0:
        return lat, lon
    a = 6378245.0
    ee = 0.00669342162296594323
    dlat = transform_lat(lon - 105.0, lat - 35.0)
    dlon = transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * math.pi)
    dlon = (dlon * 180.0) / (a / sqrtmagic * math.cos(radlat) * math.pi)
    return lat + dlat, lon + dlon

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

def calculate_distance(lat1, lon1, lat2, lon2):
    """计算两点间距离（米）- 使用Haversine公式"""
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def calculate_bearing(lat1, lon1, lat2, lon2):
    """计算方位角"""
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(lat2_rad)
    y = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon)
    bearing = math.atan2(x, y)
    return math.degrees(bearing)

def get_point_at_distance(lat, lon, distance_m, bearing_deg):
    """根据距离和方位角计算新坐标"""
    R = 6371000
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    bearing_rad = math.radians(bearing_deg)
    
    new_lat_rad = math.asin(math.sin(lat_rad) * math.cos(distance_m/R) + 
                             math.cos(lat_rad) * math.sin(distance_m/R) * math.cos(bearing_rad))
    new_lon_rad = lon_rad + math.atan2(math.sin(bearing_rad) * math.sin(distance_m/R) * math.cos(lat_rad),
                                        math.cos(distance_m/R) - math.sin(lat_rad) * math.sin(new_lat_rad))
    
    return math.degrees(new_lat_rad), math.degrees(new_lon_rad)

# -------------------------- 航线规划算法 --------------------------
def check_line_crosses_obstacle(p1, p2, obstacle_coords):
    """检查线段是否与障碍物相交"""
    line = LineString([p1[::-1], p2[::-1]])  # 转换为(lon, lat)
    obstacle_polygon = Polygon(obstacle_coords[::-1] if len(obstacle_coords) > 2 else obstacle_coords)
    return line.intersects(obstacle_polygon)

def find_avoidance_points(obstacle_coords, p1, p2, safe_radius_m, direction="left"):
    """计算绕行点"""
    # 计算障碍物中心点
    center_lat = sum([c[0] for c in obstacle_coords]) / len(obstacle_coords)
    center_lon = sum([c[1] for c in obstacle_coords]) / len(obstacle_coords)
    
    # 计算AB方向
    bearing_ab = calculate_bearing(p1[0], p1[1], p2[0], p2[1])
    
    # 根据方向计算绕行角度
    if direction == "left":
        detour_bearing = bearing_ab + 90
    else:
        detour_bearing = bearing_ab - 90
    
    # 计算绕行点（距离中心safe_radius米）
    detour_lat, detour_lon = get_point_at_distance(center_lat, center_lon, safe_radius * 2, detour_bearing)
    
    return detour_lat, detour_lon

def calculate_optimal_route(obstacle_coords, p1, p2, safe_radius_m):
    """计算最佳航线（左右绕行中距离较短的）"""
    left_lat, left_lon = find_avoidance_points(obstacle_coords, p1, p2, safe_radius_m, "left")
    right_lat, right_lon = find_avoidance_points(obstacle_coords, p1, p2, safe_radius_m, "right")
    
    # 计算两种绕行方案的总距离
    left_dist = (calculate_distance(p1[0], p1[1], left_lat, left_lon) + 
                 calculate_distance(left_lat, left_lon, p2[0], p2[1]))
    right_dist = (calculate_distance(p1[0], p1[1], right_lat, right_lon) + 
                  calculate_distance(right_lat, right_lon, p2[0], p2[1]))
    
    if left_dist <= right_dist:
        return (left_lat, left_lon), "最佳航线（左绕行）"
    else:
        return (right_lat, right_lon), "最佳航线（右绕行）"

def plan_route(a_point, b_point, obstacles, flight_height, safe_radius):
    """规划完整航线"""
    if not a_point["set"] or not b_point["set"]:
        return None, "请先设置A点和B点"
    
    waypoints = [(a_point["lat"], a_point["lon"])]
    route_description = []
    
    current_point = (a_point["lat"], a_point["lon"])
    target_point = (b_point["lat"], b_point["lon"])
    
    # 按距离排序障碍物（从A到B方向）
    obstacles_with_dist = []
    for obs in obstacles:
        center_lat = sum([c[0] for c in obs["coords"]]) / len(obs["coords"])
        center_lon = sum([c[1] for c in obs["coords"]]) / len(obs["coords"])
        dist_to_route = min([calculate_distance(current_point[0], current_point[1], c[0], c[1]) for c in obs["coords"]])
        obstacles_with_dist.append((obs, dist_to_route))
    
    obstacles_with_dist.sort(key=lambda x: x[1])
    
    for obs, _ in obstacles_with_dist:
        # 检查当前点到目标点的线段是否穿过障碍物
        if check_line_crosses_obstacle(current_point, target_point, obs["coords"]):
            if flight_height > obs["height"]:
                # 直接飞跃
                route_description.append(f"✅ 飞跃障碍物（高{obs['height']}m）")
            else:
                # 需要绕行
                # 找到绕过当前障碍物的路径
                best_waypoint, desc = calculate_optimal_route(obs["coords"], current_point, target_point, safe_radius)
                route_description.append(f"🔄 {desc}（障碍物高{obs['height']}m）")
                waypoints.append(best_waypoint)
                current_point = best_waypoint
    
    waypoints.append(target_point)
    route_description.append("🏁 到达终点B")
    
    return waypoints, route_description

# -------------------------- 障碍物持久化函数 --------------------------
def save_obstacles_to_file():
    """保存障碍物配置到文件"""
    config = {
        "obstacles": st.session_state.obstacles,
        "save_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "version": "v12.2 障碍物持久化版",
        "flight_height": st.session_state.flight_height,
        "safe_radius": st.session_state.safe_radius
    }
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    st.success(f"✅ 已保存 {len(st.session_state.obstacles)} 个障碍物到 {CONFIG_FILE}")

def load_obstacles_from_file():
    """从文件加载障碍物配置"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        st.session_state.obstacles = config.get("obstacles", [])
        st.session_state.flight_height = config.get("flight_height", 10)
        st.session_state.safe_radius = config.get("safe_radius", 5)
        st.success(f"✅ 已加载 {len(st.session_state.obstacles)} 个障碍物，保存时间: {config.get('save_time', '未知')}")
        st.rerun()
    else:
        st.warning("⚠️ 配置文件不存在，请先保存")

def clear_all_obstacles():
    """清除所有障碍物"""
    st.session_state.obstacles = []
    st.session_state.planned_route = None
    st.success("✅ 已清除所有障碍物")
    st.rerun()

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
    st.write("输入坐标系")
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
    if st.session_state.obstacles:
        st.write(f"障碍物数量: {len(st.session_state.obstacles)}")
    if st.session_state.current_page == "飞行监控":
        st.write(f"无人机状态: {st.session_state.flight_data.iloc[-1]['状态']}")
        st.write(f"当前电量: {st.session_state.flight_data.iloc[-1]['电量(%)']}%")

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
        st.session_state.safe_radius = st.number_input("🛡️ 安全半径(m)", value=st.session_state.safe_radius, min_value=1, max_value=50, step=1)
        
        if set_a:
            st.session_state.a_point = {"lat": a_lat, "lon": a_lon, "set": True}
            st.session_state.planned_route = None
        else:
            st.session_state.a_point["set"] = False
        if set_b:
            st.session_state.b_point = {"lat": b_lat, "lon": b_lon, "set": True}
            st.session_state.planned_route = None
        else:
            st.session_state.b_point["set"] = False
        
        # 航线规划按钮
        if st.button("🎯 智能规划航线", type="primary", use_container_width=True):
            if st.session_state.a_point["set"] and st.session_state.b_point["set"]:
                waypoints, desc = plan_route(
                    st.session_state.a_point, 
                    st.session_state.b_point, 
                    st.session_state.obstacles,
                    st.session_state.flight_height,
                    st.session_state.safe_radius
                )
                if waypoints:
                    st.session_state.planned_route = waypoints
                    st.success("✅ 航线规划完成！")
                    with st.expander("📋 航线详情"):
                        for d in desc:
                            st.write(d)
                else:
                    st.warning(desc)
            else:
                st.warning("请先设置A点和B点")
        
        st.divider()
        
        st.subheader("🚧 障碍物配置持久化")
        st.caption(f"配置文件: {os.path.abspath(CONFIG_FILE)} | 版本: v12.2")
        
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
            config_data = {
                "obstacles": st.session_state.obstacles,
                "flight_height": st.session_state.flight_height,
                "safe_radius": st.session_state.safe_radius,
                "version": "v12.2"
            }
            st.download_button(
                label="📥 下载配置",
                data=json.dumps(config_data, ensure_ascii=False, indent=2),
                file_name="obstacle_config.json",
                mime="application/json",
                use_container_width=True
            )
        
        if st.session_state.obstacles:
            st.info(f"📊 共 {len(st.session_state.obstacles)} 个障碍物")
            
            # 障碍物高度设置
            st.subheader("🏔️ 障碍物高度设置")
            for i, obs in enumerate(st.session_state.obstacles):
                col_h1, col_h2 = st.columns([3, 1])
                with col_h1:
                    new_height = st.number_input(
                        f"障碍物 {i+1} 高度(m)", 
                        value=obs.get("height", 10), 
                        min_value=0, 
                        max_value=200,
                        key=f"obs_height_{i}"
                    )
                with col_h2:
                    if st.button(f"🗑️ 删除", key=f"del_obs_{i}"):
                        st.session_state.obstacles.pop(i)
                        st.rerun()
                st.session_state.obstacles[i]["height"] = new_height

    with col_map:
        st.header("🗺️ 航线规划地图")
        
        # 坐标系转换
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
        
        # 添加绘制控件
        draw = plugins.Draw(
            export=True,
            position='topleft',
            draw_options={
                'polygon': {'allowIntersection': False, 'showArea': True, 'shapeOptions': {'color': '#ff0000', 'weight': 3}},
                'polyline': False,
                'rectangle': False,
                'circle': False,
                'marker': False,
                'circlemarker': False
            },
            edit_options={'edit': True, 'remove': True}
        )
        draw.add_to(m)
        
        # 绘制已保存的障碍物
        for i, obstacle in enumerate(st.session_state.obstacles):
            height = obstacle.get("height", 10)
            folium.Polygon(
                locations=obstacle["coords"],
                color="red",
                weight=3,
                fill=True,
                fill_color="red",
                fill_opacity=0.3,
                popup=f"障碍物 {i+1}\n高度: {height}m\n{'⚠️ 需绕行' if height >= st.session_state.flight_height else '✅ 可飞跃'}"
            ).add_to(m)
            
            # 添加高度标注
            center_lat_obs = sum([c[0] for c in obstacle["coords"]]) / len(obstacle["coords"])
            center_lon_obs = sum([c[1] for c in obstacle["coords"]]) / len(obstacle["coords"])
            folium.map.Marker(
                [center_lat_obs, center_lon_obs],
                icon=folium.DivIcon(html=f'<div style="font-size: 10pt; color: red; font-weight: bold;">{height}m</div>')
            ).add_to(m)
        
        # 绘制A点和B点
        if st.session_state.a_point["set"]:
            folium.Marker(
                location=[st.session_state.a_point["lat"], st.session_state.a_point["lon"]],
                popup=f"起点A\n高度: {st.session_state.flight_height}m",
                icon=folium.Icon(color="green", icon="play", prefix='fa')
            ).add_to(m)
        if st.session_state.b_point["set"]:
            folium.Marker(
                location=[st.session_state.b_point["lat"], st.session_state.b_point["lon"]],
                popup="终点B",
                icon=folium.Icon(color="blue", icon="flag-checkered", prefix='fa')
            ).add_to(m)
        
        # 绘制规划的航线
        if st.session_state.planned_route:
            folium.PolyLine(
                locations=st.session_state.planned_route,
                color="green",
                weight=4,
                opacity=0.9,
                popup="智能规划航线"
            ).add_to(m)
            
            # 添加航点标记
            for i, wp in enumerate(st.session_state.planned_route):
                if 0 < i < len(st.session_state.planned_route) - 1:
                    folium.Marker(
                        location=[wp[0], wp[1]],
                        popup=f"航点 {i}",
                        icon=folium.Icon(color="orange", icon="info-sign", prefix='fa')
                    ).add_to(m)
        else:
            # 绘制简单AB连线
            if st.session_state.a_point["set"] and st.session_state.b_point["set"]:
                folium.PolyLine(
                    locations=[[st.session_state.a_point["lat"], st.session_state.a_point["lon"]],
                               [st.session_state.b_point["lat"], st.session_state.b_point["lon"]]],
                    color="gray",
                    weight=2,
                    opacity=0.5,
                    popup="原始连线"
                ).add_to(m)
        
        # 渲染地图并获取绘制的数据
        output = st_folium(m, width="100%", height=650, key="route_map")
        
        # 处理新绘制的多边形
        if output and output.get("last_active_drawing"):
            drawing = output["last_active_drawing"]
            if drawing.get("geometry", {}).get("type") == "Polygon":
                coordinates = drawing["geometry"]["coordinates"][0]
                polygon_coords = [[coord[1], coord[0]] for coord in coordinates]
                st.session_state.obstacles.append({
                    "coords": polygon_coords,
                    "height": 10  # 默认高度10米
                })
                st.success(f"✅ 已添加障碍物，当前共 {len(st.session_state.obstacles)} 个，请设置高度")
                st.rerun()

# -------------------------- 页面2：飞行监控 --------------------------
elif st.session_state.current_page == "飞行监控":
    st.header("📡 无人机飞行监控")
    
    # 心跳包状态
    heartbeat_col1, heartbeat_col2, heartbeat_col3 = st.columns(3)
    with heartbeat_col1:
        st.metric("💓 心跳状态", "正常" if st.session_state.flight_data.iloc[-1]["电量(%)"] > 0 else "异常")
    with heartbeat_col2:
        st.metric("📡 信号强度", f"{min(100, st.session_state.flight_data.iloc[-1]['电量(%)'] + 15)}%")
    with heartbeat_col3:
        st.metric("🕐 最后心跳", st.session_state.flight_data.iloc[-1]["时间"])
    
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
        
        # 坐标转换显示
        display_lat = latest["纬度"]
        display_lon = latest["经度"]
        if coord_system == "GCJ-02(高德/百度)":
            display_lat, display_lon = wgs84_to_gcj02(display_lat, display_lon)
        
        m = folium.Map(
            location=[display_lat, display_lon],
            zoom_start=18,
            tiles=tile_url,
            attr=tile_attr,
            control_scale=True
        )
        
        # 绘制障碍物
        for i, obstacle in enumerate(st.session_state.obstacles):
            folium.Polygon(
                locations=obstacle["coords"],
                color="red",
                weight=2,
                fill=True,
                fill_color="red",
                fill_opacity=0.3,
                popup=f"障碍物 {i+1}\n高度: {obstacle.get('height', 10)}m"
            ).add_to(m)
        
        # 绘制历史飞行轨迹
        if len(st.session_state.flight_data) > 1:
            track_points = []
            for _, row in st.session_state.flight_data.iterrows():
                lat = row["纬度"]
                lon = row["经度"]
                if coord_system == "GCJ-02(高德/百度)":
                    lat, lon = wgs84_to_gcj02(lat, lon)
                track_points.append([lat, lon])
            
            folium.PolyLine(
                locations=track_points,
                color="blue",
                weight=2,
                opacity=0.7,
                popup="飞行轨迹"
            ).add_to(m)
        
        folium.Marker(
            location=[display_lat, display_lon],
            popup=f"当前位置\n高度: {latest['高度(m)']}m\n速度: {latest['速度(m/s)']}m/s\n电量: {latest['电量(%)']}%",
            icon=folium.Icon(color="red", icon="plane", prefix='fa')
        ).add_to(m)
        
        st_folium(m, width="100%", height=500, key="flight_map")
        
        col_update1, col_update2 = st.columns(2)
        with col_update1:
            if st.button("🔄 更新飞行数据", use_container_width=True):
                new_lat = latest["纬度"] + 0.00005
                new_lon = latest["经度"] + 0.00005
                new_row = {
                    "时间": datetime.now().strftime("%H:%M:%S"),
                    "纬度": new_lat,
                    "经度": new_lon,
                    "高度(m)": round(latest["高度(m)"] + 0.2, 1),
                    "速度(m/s)": round(latest["速度(m/s)"] + 0.1, 1),
                    "电量(%)": max(latest["电量(%)"] - 1, 0),
                    "状态": "正常飞行" if latest["电量(%)"] > 20 else "低电量告警"
                }
                st.session_state.flight_data = pd.concat([st.session_state.flight_data, pd.DataFrame([new_row])], ignore_index=True)
                if len(st.session_state.flight_data) > 100:
                    st.session_state.flight_data = st.session_state.flight_data.tail(100)
                st.rerun()
        
        with col_update2:
            if st.button("🔄 模拟心跳包", use_container_width=True):
                st.toast("💓 心跳包已发送", icon="💓")
    
    with col_data:
        st.subheader("📊 实时参数")
        latest = st.session_state.flight_data.iloc[-1]
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric(label="📏 高度(m)", value=latest["高度(m)"], delta=f"{latest['高度(m)'] - st.session_state.flight_data.iloc[-2]['高度(m)'] if len(st.session_state.flight_data) > 1 else 0:.1f}")
            st.metric(label="🔋 电量(%)", value=latest["电量(%)"], delta=f"-1")
        with col2:
            st.metric(label="⚡ 速度(m/s)", value=latest["速度(m/s)"])
            st.metric(label="📍 状态", value=latest["状态"])
        
        st.divider()
        
        st.subheader("📍 当前位置")
        st.write(f"纬度: {latest['纬度']:.6f}")
        st.write(f"经度: {latest['经度']:.6f}")
        st.write(f"坐标系: {coord_system}")
        
        if st.session_state.obstacles:
            st.divider()
            st.subheader("🚧 障碍物列表")
            for i, obs in enumerate(st.session_state.obstacles):
                st.write(f"障碍物 {i+1}: {len(obs['coords'])} 个顶点, 高度 {obs.get('height', 10)}m")
        
        st.divider()
        st.subheader("📋 飞行历史")
        st.dataframe(st.session_state.flight_data.tail(10), use_container_width=True, hide_index=True)
