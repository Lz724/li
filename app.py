import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
from datetime import datetime
import json
import os
import math
from folium import plugins
from shapely.geometry import Point, Polygon, LineString
from shapely.ops import nearest_points

# -------------------------- 页面全局配置 --------------------------
st.set_page_config(
    page_title="无人机智能化应用",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------- 坐标转换函数（WGS84转GCJ02）--------------------------
def wgs84_to_gcj02(lat, lon):
    """WGS84转GCJ02坐标系（高德/百度）"""
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
    
    dlat = transform_lat(lon - 105.0, lat - 35.0)
    dlon = transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * math.pi)
    dlon = (dlon * 180.0) / (a / sqrtmagic * math.cos(radlat) * math.pi)
    return lat + dlat, lon + dlon

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
        "状态": ["正常飞行"],
        "心跳时间": [datetime.now().strftime("%H:%M:%S")]
    })
if "obstacles" not in st.session_state:
    st.session_state.obstacles = []  # 存储障碍物 {"polygon": [[lat,lon],...], "height": 20}
if "flight_height" not in st.session_state:
    st.session_state.flight_height = 10
if "safety_radius" not in st.session_state:
    st.session_state.safety_radius = 5
if "planned_route" not in st.session_state:
    st.session_state.planned_route = None
if "route_strategy" not in st.session_state:
    st.session_state.route_strategy = "最佳航线"
if "last_heartbeat" not in st.session_state:
    st.session_state.last_heartbeat = datetime.now()

# -------------------------- 配置文件路径 --------------------------
CONFIG_FILE = "obstacle_config.json"

# -------------------------- 障碍物持久化函数 --------------------------
def save_obstacles_to_file():
    """保存障碍物配置到文件（包含高度信息）"""
    config = {
        "obstacles": st.session_state.obstacles,
        "save_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "version": "v12.2 障碍物持久化版"
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
        st.success(f"✅ 已加载 {len(st.session_state.obstacles)} 个障碍物，保存时间: {config.get('save_time', '未知')}")
        st.rerun()
    else:
        st.warning("⚠️ 配置文件不存在，请先保存")

def clear_all_obstacles():
    """清除所有障碍物"""
    st.session_state.obstacles = []
    st.success("✅ 已清除所有障碍物")
    st.rerun()

# -------------------------- 智能航线规划函数 --------------------------
def calculate_distance(lat1, lon1, lat2, lon2):
    """计算两点间距离（米）"""
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def check_line_intersects_obstacle(line_start, line_end, obstacle_polygon):
    """检查航线是否与障碍物相交"""
    line = LineString([line_start, line_end])
    polygon = Polygon(obstacle_polygon)
    return line.intersects(polygon)

def find_detour_waypoints(start, end, obstacle_polygon, side='left'):
    """计算绕行障碍物的航点"""
    polygon = Polygon(obstacle_polygon)
    centroid = centroid = (polygon.centroid.x, polygon.centroid.y)
    
    # 计算障碍物边界半径
    bounds = polygon.bounds
    radius = max(bounds[2] - bounds[0], bounds[3] - bounds[1]) / 2
    
    # 计算绕行角度
    start_angle = math.atan2(start[1] - centroid[1], start[0] - centroid[0])
    end_angle = math.atan2(end[1] - centroid[1], end[0] - centroid[0])
    
    waypoints = [start]
    
    # 根据绕行方向生成中间点
    if side == 'left':
        angle_step = 15 if start_angle < end_angle else -15
        angles = []
        current = start_angle
        if start_angle < end_angle:
            while current < end_angle:
                angles.append(current)
                current += math.radians(angle_step)
        else:
            while current > end_angle:
                angles.append(current)
                current -= math.radians(abs(angle_step))
        angles.append(end_angle)
        
        for angle in angles:
            x = centroid[0] + radius * 1.2 * math.cos(angle)
            y = centroid[1] + radius * 1.2 * math.sin(angle)
            waypoints.append([y, x])
    else:  # right
        angle_step = -15 if start_angle < end_angle else 15
        angles = []
        current = start_angle
        if start_angle < end_angle:
            while current < end_angle + math.radians(5):
                angles.append(current)
                current -= math.radians(abs(angle_step))
        else:
            while current > end_angle - math.radians(5):
                angles.append(current)
                current += math.radians(abs(angle_step))
        angles.append(end_angle)
        
        for angle in angles:
            x = centroid[0] + radius * 1.2 * math.cos(angle)
            y = centroid[1] + radius * 1.2 * math.sin(angle)
            waypoints.append([y, x])
    
    waypoints.append(end)
    return waypoints

def calculate_route_distance(waypoints):
    """计算航线总距离"""
    total = 0
    for i in range(len(waypoints)-1):
        total += calculate_distance(waypoints[i][0], waypoints[i][1], waypoints[i+1][0], waypoints[i+1][1])
    return total

def plan_intelligent_route():
    """智能航线规划主函数"""
    if not st.session_state.a_point["set"] or not st.session_state.b_point["set"]:
        st.warning("⚠️ 请先设置起点A和终点B")
        return None
    
    start = (st.session_state.a_point["lat"], st.session_state.a_point["lon"])
    end = (st.session_state.b_point["lat"], st.session_state.b_point["lon"])
    flight_height = st.session_state.flight_height
    safety_radius = st.session_state.safety_radius / 111000  # 转换为度
    
    routes = []
    current_pos = start
    
    for i, obstacle_data in enumerate(st.session_state.obstacles):
        obstacle_polygon = obstacle_data["polygon"]
        obstacle_height = obstacle_data.get("height", 20)
        
        # 扩展安全边界
        expanded_polygon = expand_polygon(obstacle_polygon, safety_radius)
        
        # 检查航线是否与障碍物相交
        if check_line_intersects_obstacle(current_pos, end, expanded_polygon):
            if flight_height > obstacle_height:
                # 飞跃障碍物
                routes.append({
                    "type": "fly_over",
                    "start": current_pos,
                    "end": end,
                    "description": f"✈️ 飞跃障碍物{i+1} (飞行高度{flight_height}m > 障碍物高度{obstacle_height}m)",
                    "color": "green"
                })
                current_pos = end
                break
            else:
                # 需要绕行
                if st.session_state.route_strategy == "向左绕行":
                    waypoints = find_detour_waypoints(current_pos, end, expanded_polygon, 'left')
                    routes.append({
                        "type": "detour_left",
                        "waypoints": waypoints,
                        "description": f"⬅️ 向左绕行障碍物{i+1} (飞行高度{flight_height}m ≤ 障碍物高度{obstacle_height}m)",
                        "color": "orange"
                    })
                    current_pos = waypoints[-1]
                elif st.session_state.route_strategy == "向右绕行":
                    waypoints = find_detour_waypoints(current_pos, end, expanded_polygon, 'right')
                    routes.append({
                        "type": "detour_right",
                        "waypoints": waypoints,
                        "description": f"➡️ 向右绕行障碍物{i+1} (飞行高度{flight_height}m ≤ 障碍物高度{obstacle_height}m)",
                        "color": "orange"
                    })
                    current_pos = waypoints[-1]
                else:  # 最佳航线
                    # 计算左右绕行距离，选择较短的
                    left_waypoints = find_detour_waypoints(current_pos, end, expanded_polygon, 'left')
                    right_waypoints = find_detour_waypoints(current_pos, end, expanded_polygon, 'right')
                    
                    left_distance = calculate_route_distance(left_waypoints)
                    right_distance = calculate_route_distance(right_waypoints)
                    
                    if left_distance <= right_distance:
                        routes.append({
                            "type": "best_detour_left",
                            "waypoints": left_waypoints,
                            "description": f"🏆 最佳航线(向左绕行)障碍物{i+1} - 距离{left_distance:.0f}m",
                            "color": "purple"
                        })
                        current_pos = left_waypoints[-1]
                    else:
                        routes.append({
                            "type": "best_detour_right",
                            "waypoints": right_waypoints,
                            "description": f"🏆 最佳航线(向右绕行)障碍物{i+1} - 距离{right_distance:.0f}m",
                            "color": "purple"
                        })
                        current_pos = right_waypoints[-1]
    
    # 添加最后直线段
    if current_pos != end:
        routes.append({
            "type": "straight",
            "start": current_pos,
            "end": end,
            "description": "➡️ 直线飞行至终点",
            "color": "blue"
        })
    
    return routes

def expand_polygon(polygon_coords, buffer_deg):
    """扩展多边形（安全边界）"""
    try:
        poly = Polygon(polygon_coords)
        expanded = poly.buffer(buffer_deg)
        if expanded.geom_type == 'Polygon':
            return [[coord[1], coord[0]] for coord in expanded.exterior.coords]
        else:
            return polygon_coords
    except:
        return polygon_coords

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
    st.write(f"A点状态: {'✅ 已设置' if st.session_state.a_point['set'] else '❌ 未设置'}")
    st.write(f"B点状态: {'✅ 已设置' if st.session_state.b_point['set'] else '❌ 未设置'}")
    
    # 心跳包状态显示
    time_since_last = (datetime.now() - st.session_state.last_heartbeat).total_seconds()
    if time_since_last < 5:
        st.write(f"💓 心跳包: 🟢 正常 ({time_since_last:.1f}秒前)")
    else:
        st.write(f"💓 心跳包: 🔴 异常 ({time_since_last:.1f}秒前)")
    
    if st.session_state.current_page == "飞行监控":
        st.write(f"🚁 无人机状态: {st.session_state.flight_data.iloc[-1]['状态']}")
        st.write(f"🔋 当前电量: {st.session_state.flight_data.iloc[-1]['电量(%)']}%")

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
        st.session_state.flight_height = st.number_input("飞行高度(m)", value=st.session_state.flight_height, min_value=5, max_value=200, step=5)
        st.session_state.safety_radius = st.number_input("安全半径(m)", value=st.session_state.safety_radius, min_value=1, max_value=50, step=1)
        
        st.subheader("🔄 航线策略")
        route_strategy = st.selectbox(
            "绕行策略",
            ["最佳航线", "向左绕行", "向右绕行"],
            index=["最佳航线", "向左绕行", "向右绕行"].index(st.session_state.route_strategy)
        )
        st.session_state.route_strategy = route_strategy
        
        if st.button("✈️ 智能规划航线", use_container_width=True, type="primary"):
            with st.spinner("🔄 正在规划航线..."):
                routes = plan_intelligent_route()
                if routes:
                    st.session_state.planned_route = routes
                    total_dist = sum([calculate_route_distance([r['start'], r['end']]) if 'start' in r else calculate_route_distance(r['waypoints']) for r in routes if 'start' in r or 'waypoints' in r])
                    st.success(f"✅ 航线规划完成！总距离: {total_dist:.0f}m")
                    st.rerun()
        
        if set_a:
            st.session_state.a_point = {"lat": a_lat, "lon": a_lon, "set": True}
        else:
            st.session_state.a_point["set"] = False
        if set_b:
            st.session_state.b_point = {"lat": b_lat, "lon": b_lon, "set": True}
        else:
            st.session_state.b_point["set"] = False
        
        st.divider()
        
        st.subheader("🚧 障碍物配置")
        st.caption(f"配置文件: {os.path.abspath(CONFIG_FILE)} | 版本: v12.2")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("💾 一键保存", use_container_width=True):
                save_obstacles_to_file()
        with col_btn2:
            if st.button("📂 加载配置", use_container_width=True):
                load_obstacles_from_file()
        
        col_btn3, col_btn4 = st.columns(2)
        with col_btn3:
            if st.button("🗑️ 清除全部", use_container_width=True):
                clear_all_obstacles()
        with col_btn4:
            config_json = json.dumps({
                "obstacles": st.session_state.obstacles,
                "version": "v12.2",
                "save_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }, ensure_ascii=False, indent=2)
            st.download_button(
                label="📥 下载JSON",
                data=config_json,
                file_name="obstacle_config.json",
                mime="application/json",
                use_container_width=True
            )
        
        if st.session_state.obstacles:
            st.info(f"📊 障碍物数量: {len(st.session_state.obstacles)}")
            for i, obs in enumerate(st.session_state.obstacles):
                height = obs.get("height", 20)
                st.caption(f"🚧 障碍物{i+1}: 高度{height}m, {len(obs['polygon'])}个顶点")
        
        if st.session_state.planned_route:
            st.divider()
            st.subheader("📋 航线规划结果")
            for i, segment in enumerate(st.session_state.planned_route):
                st.info(f"{i+1}. {segment['description']}")

    with col_map:
        st.header("🗺️ 智能航线规划地图")
        
        # 坐标转换和地图配置
        if coord_system == "GCJ-02(高德/百度)":
            tile_url = "https://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"
            tile_attr = "&copy; 高德地图"
            # 转换坐标
            center_lat, center_lon = st.session_state.a_point["lat"], st.session_state.a_point["lon"]
            if st.session_state.a_point["set"]:
                center_lat, center_lon = wgs84_to_gcj02(st.session_state.a_point["lat"], st.session_state.a_point["lon"])
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
        for i, obstacle_data in enumerate(st.session_state.obstacles):
            polygon_coords = obstacle_data["polygon"]
            height = obstacle_data.get("height", 20)
            
            # 坐标转换（如果需要）
            display_coords = polygon_coords
            if coord_system == "GCJ-02(高德/百度)":
                display_coords = [[wgs84_to_gcj02(lat, lon)[0], wgs84_to_gcj02(lat, lon)[1]] for lat, lon in polygon_coords]
            
            folium.Polygon(
                locations=display_coords,
                color="red",
                weight=3,
                fill=True,
                fill_color="red",
                fill_opacity=0.3,
                popup=f"🚧 障碍物 {i+1}\n📏 高度: {height}m\n📍 顶点数: {len(polygon_coords)}"
            ).add_to(m)
            
            # 添加高度标注
            try:
                center = Polygon(polygon_coords).centroid
                center_lat_gcj, center_lon_gcj = wgs84_to_gcj02(center.y, center.x) if coord_system == "GCJ-02(高德/百度)" else (center.y, center.x)
                folium.Marker(
                    location=[center_lat_gcj, center_lon_gcj],
                    icon=folium.DivIcon(html=f'<div style="font-size: 11px; font-weight: bold; color: red; background: white; padding: 2px 5px; border-radius: 10px;">🚧{height}m</div>')
                ).add_to(m)
            except:
                pass
        
        # 绘制智能规划航线
        if st.session_state.planned_route:
            for segment in st.session_state.planned_route:
                if segment["type"] in ["fly_over", "straight"]:
                    # 坐标转换
                    start_coords = segment["start"]
                    end_coords = segment["end"]
                    if coord_system == "GCJ-02(高德/百度)":
                        start_coords = wgs84_to_gcj02(segment["start"][0], segment["start"][1])
                        end_coords = wgs84_to_gcj02(segment["end"][0], segment["end"][1])
                    
                    folium.PolyLine(
                        locations=[[start_coords[0], start_coords[1]], [end_coords[0], end_coords[1]]],
                        color=segment["color"],
                        weight=4,
                        opacity=0.8,
                        popup=segment["description"]
                    ).add_to(m)
                elif "waypoints" in segment:
                    # 坐标转换
                    display_waypoints = []
                    for wp in segment["waypoints"]:
                        if coord_system == "GCJ-02(高德/百度)":
                            gcj_lat, gcj_lon = wgs84_to_gcj02(wp[0], wp[1])
                            display_waypoints.append([gcj_lat, gcj_lon])
                        else:
                            display_waypoints.append([wp[0], wp[1]])
                    
                    folium.PolyLine(
                        locations=display_waypoints,
                        color=segment["color"],
                        weight=4,
                        opacity=0.8,
                        popup=segment["description"]
                    ).add_to(m)
                    
                    # 标记绕行点
                    for wp in display_waypoints[1:-1]:
                        folium.CircleMarker(
                            location=[wp[0], wp[1]],
                            radius=4,
                            color="yellow",
                            fill=True,
                            popup="航点"
                        ).add_to(m)
        
        # 绘制A/B点
        if st.session_state.a_point["set"]:
            a_coords = (st.session_state.a_point["lat"], st.session_state.a_point["lon"])
            if coord_system == "GCJ-02(高德/百度)":
                a_coords = wgs84_to_gcj02(st.session_state.a_point["lat"], st.session_state.a_point["lon"])
            
            folium.Marker(
                location=[a_coords[0], a_coords[1]],
                popup=f"📍 起点A\n✈️ 高度: {st.session_state.flight_height}m\n🛡️ 安全半径: {st.session_state.safety_radius}m",
                icon=folium.Icon(color="green", icon="play", prefix='fa')
            ).add_to(m)
            
            # 安全半径圆
            folium.Circle(
                radius=st.session_state.safety_radius,
                location=[a_coords[0], a_coords[1]],
                color="green",
                fill=False,
                weight=2,
                popup=f"安全半径: {st.session_state.safety_radius}m"
            ).add_to(m)
        
        if st.session_state.b_point["set"]:
            b_coords = (st.session_state.b_point["lat"], st.session_state.b_point["lon"])
            if coord_system == "GCJ-02(高德/百度)":
                b_coords = wgs84_to_gcj02(st.session_state.b_point["lat"], st.session_state.b_point["lon"])
            
            folium.Marker(
                location=[b_coords[0], b_coords[1]],
                popup="🏁 终点B",
                icon=folium.Icon(color="blue", icon="flag-checkered", prefix='fa')
            ).add_to(m)
        
        # 渲染地图并处理绘制的多边形
        output = st_folium(m, width="100%", height=650, key="route_map")
        
        # 处理新绘制的多边形并设置高度
        if output and output.get("last_active_drawing"):
            drawing = output["last_active_drawing"]
            if drawing.get("geometry", {}).get("type") == "Polygon":
                coordinates = drawing["geometry"]["coordinates"][0]
                polygon_coords = [[coord[1], coord[0]] for coord in coordinates]
                st.session_state.temp_polygon = polygon_coords
                st.session_state.show_height_dialog = True
        
        # 高度设置对话框
        if st.session_state.get("show_height_dialog", False):
            with st.expander("🏔️ 设置障碍物高度", expanded=True):
                obs_height = st.number_input("障碍物高度(m)", min_value=1, max_value=200, value=20, step=5)
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✅ 确认添加"):
                        st.session_state.obstacles.append({
                            "polygon": st.session_state.temp_polygon,
                            "height": obs_height
                        })
                        st.session_state.show_height_dialog = False
                        st.success(f"✅ 已添加障碍物，高度{obs_height}m")
                        st.rerun()
                with col2:
                    if st.button("❌ 取消"):
                        st.session_state.show_height_dialog = False
                        st.rerun()

# -------------------------- 页面2：飞行监控 --------------------------
elif st.session_state.current_page == "飞行监控":
    st.header("📡 无人机飞行监控")
    
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
        display_lat, display_lon = latest["纬度"], latest["经度"]
        if coord_system == "GCJ-02(高德/百度)":
            display_lat, display_lon = wgs84_to_gcj02(latest["纬度"], latest["经度"])
        
        m = folium.Map(
            location=[display_lat, display_lon],
            zoom_start=18,
            tiles=tile_url,
            attr=tile_attr,
            control_scale=True
        )
        
        # 绘制障碍物
        for i, obstacle_data in enumerate(st.session_state.obstacles):
            polygon_coords = obstacle_data["polygon"]
            height = obstacle_data.get("height", 20)
            
            display_coords = polygon_coords
            if coord_system == "GCJ-02(高德/百度)":
                display_coords = [[wgs84_to_gcj02(lat, lon)[0], wgs84_to_gcj02(lat, lon)[1]] for lat, lon in polygon_coords]
            
            folium.Polygon(
                locations=display_coords,
                color="red",
                weight=2,
                fill=True,
                fill_color="red",
                fill_opacity=0.3,
                popup=f"🚧 障碍物 {i+1}\n高度: {height}m"
            ).add_to(m)
        
        # 绘制历史飞行轨迹
        if len(st.session_state.flight_data) > 1:
            history_coords = []
            for _, row in st.session_state.flight_data.iterrows():
                if coord_system == "GCJ-02(高德/百度)":
                    lat, lon = wgs84_to_gcj02(row["纬度"], row["经度"])
                else:
                    lat, lon = row["纬度"], row["经度"]
                history_coords.append([lat, lon])
            
            folium.PolyLine(
                locations=history_coords,
                color="blue",
                weight=2,
                opacity=0.7,
                popup="飞行轨迹"
            ).add_to(m)
        
        folium.Marker(
            location=[display_lat, display_lon],
            popup=f"🚁 当前位置\n📏 高度: {latest['高度(m)']}m\n⚡ 速度: {latest['速度(m/s)']}m/s\n🔋 电量: {latest['电量(%)']}%",
            icon=folium.Icon(color="red", icon="plane", prefix='fa')
        ).add_to(m)
        
        st_folium(m, width="100%", height=500, key="flight_map")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("💓 发送心跳包", use_container_width=True):
                st.session_state.last_heartbeat = datetime.now()
                st.success("✅ 心跳包已发送")
        with col2:
            if st.button("🔄 更新数据", use_container_width=True):
                new_row = {
                    "时间": datetime.now().strftime("%H:%M:%S"),
                    "纬度": latest["纬度"] + 0.00005,
                    "经度": latest["经度"] + 0.00005,
                    "高度(m)": round(latest["高度(m)"] + 0.2, 1),
                    "速度(m/s)": round(latest["速度(m/s)"] + 0.1, 1),
                    "电量(%)": max(latest["电量(%)"] - 1, 0),
                    "状态": "正常飞行" if latest["电量(%)"] > 20 else "⚠️ 低电量告警",
                    "心跳时间": datetime.now().strftime("%H:%M:%S")
                }
                st.session_state.flight_data = pd.concat([st.session_state.flight_data, pd.DataFrame([new_row])], ignore_index=True)
                st.rerun()
        with col3:
            time_since_last = (datetime.now() - st.session_state.last_heartbeat).
