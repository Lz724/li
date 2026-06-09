import streamlit as st
import folium
from streamlit_folium import st_folium, folium_static
import pandas as pd
from datetime import datetime
import json
import os
import math
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
import random

# -------------------------- 页面全局配置 --------------------------
st.set_page_config(
    page_title="无人机智能化应用 - 障碍物规避系统",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------- 坐标系转换工具 --------------------------
def gcj02_to_wgs84(lat, lon):
    """GCJ-02(火星坐标系) 转 WGS-84"""
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
    wgs_lat = lat - dlat
    wgs_lon = lon - dlon
    return wgs_lat, wgs_lon

def wgs84_to_gcj02(lat, lon):
    """WGS-84 转 GCJ-02"""
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
    gcj_lat = lat + dlat
    gcj_lon = lon + dlon
    return gcj_lat, gcj_lon

# -------------------------- 障碍物配置文件管理 --------------------------
CONFIG_FILE = "obstacle_config.json"

def load_obstacles():
    """从文件加载障碍物配置"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('obstacles', []), data.get('last_save_time', '')
        except:
            return [], ''
    return [], ''

def save_obstacles(obstacles):
    """保存障碍物配置到文件"""
    data = {
        'obstacles': obstacles,
        'last_save_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'version': 'v12.2'
    }
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data['last_save_time']

# -------------------------- 会话状态初始化 --------------------------
if "current_page" not in st.session_state:
    st.session_state.current_page = "航线规划"
if "a_point" not in st.session_state:
    st.session_state.a_point = {"lat": 32.2323, "lon": 118.749, "set": False}
if "b_point" not in st.session_state:
    st.session_state.b_point = {"lat": 32.2344, "lon": 118.749, "set": False}
if "flight_height" not in st.session_state:
    st.session_state.flight_height = 10.0
if "flight_data" not in st.session_state:
    st.session_state.flight_data = pd.DataFrame({
        "时间": [datetime.now().strftime("%H:%M:%S")],
        "纬度": [32.23335],
        "经度": [118.749],
        "高度(m)": [10.0],
        "速度(m/s)": [3.2],
        "电量(%)": [100],
        "状态": ["待命"]
    })
if "obstacles" not in st.session_state:
    # 加载持久化的障碍物配置
    saved_obstacles, save_time = load_obstacles()
    if saved_obstacles:
        st.session_state.obstacles = saved_obstacles
        st.session_state.obstacle_save_time = save_time
    else:
        # 默认添加一些示例障碍物
        st.session_state.obstacles = []
        st.session_state.obstacle_save_time = ''
if "drawing_polygon" not in st.session_state:
    st.session_state.drawing_polygon = False
if "current_polygon" not in st.session_state:
    st.session_state.current_polygon = []

# -------------------------- 侧边栏（导航+坐标系+状态） --------------------------
with st.sidebar:
    st.header("🚁 无人机智能化应用")
    st.caption("障碍物规避系统 v12.2")
    
    st.subheader("📖 功能页面")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗺️ 航线规划", type="primary" if st.session_state.current_page == "航线规划" else "secondary", use_container_width=True):
            st.session_state.current_page = "航线规划"
            st.rerun()
    with col2:
        if st.button("📡 飞行监控", type="primary" if st.session_state.current_page == "飞行监控" else "secondary", use_container_width=True):
            st.session_state.current_page = "飞行监控"
            st.rerun()
    
    st.divider()
    
    # 坐标系设置
    st.subheader("⚙️ 坐标系设置")
    coord_system = st.radio(
        "选择坐标系",
        ["WGS-84", "GCJ-02 (高德/百度)"],
        index=1,
        label_visibility="collapsed"
    )
    
    st.divider()
    
    # 系统状态
    st.subheader("✅ 系统状态")
    st.write(f"🏁 A点: {'✅ 已设置' if st.session_state.a_point['set'] else '❌ 未设置'}")
    st.write(f"🏁 B点: {'✅ 已设置' if st.session_state.b_point['set'] else '❌ 未设置'}")
    st.write(f"📏 飞行高度: {st.session_state.flight_height}m")
    st.write(f"🚧 障碍物数量: {len(st.session_state.obstacles)}")
    if st.session_state.current_page == "飞行监控":
        st.write(f"🚁 无人机状态: {st.session_state.flight_data.iloc[-1]['状态']}")
        st.write(f"🔋 电量: {st.session_state.flight_data.iloc[-1]['电量(%)']}%")

# -------------------------- 页面1：航线规划（含多边形障碍物圈选） --------------------------
if st.session_state.current_page == "航线规划":
    st.header("🗺️ 智能航线规划与障碍物管理")
    
    # 分栏布局
    col_map, col_ctrl = st.columns([2.5, 1.5])
    
    # 地图区域
    with col_map:
        st.subheader("🗺️ 交互式地图")
        st.caption("💡 提示：点击地图开始绘制多边形障碍物，双击完成绘制")
        
        # 确定地图中心点和瓦片
        center_lat, center_lon = 32.23335, 118.749
        if coord_system == "GCJ-02 (高德/百度)":
            # 使用高德卫星图
            tile_url = "https://webst01.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}"
            tile_attr = "&copy; 高德地图"
            # 转换坐标用于显示
            display_lat, display_lon = st.session_state.a_point["lat"], st.session_state.a_point["lon"]
            if st.session_state.a_point["set"]:
                center_lat, center_lon = st.session_state.a_point["lat"], st.session_state.a_point["lon"]
        else:
            # OpenStreetMap
            tile_url = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            tile_attr = "&copy; OpenStreetMap"
            if st.session_state.a_point["set"]:
                center_lat, center_lon = st.session_state.a_point["lat"], st.session_state.a_point["lon"]
        
        # 创建地图
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=18,
            tiles=tile_url,
            attr=tile_attr,
            control_scale=True
        )
        
        # 绘制A点
        if st.session_state.a_point["set"]:
            folium.Marker(
                location=[st.session_state.a_point["lat"], st.session_state.a_point["lon"]],
                popup=f"起点A\n{st.session_state.a_point['lat']:.4f}, {st.session_state.a_point['lon']:.4f}",
                icon=folium.Icon(color="red", icon="play", prefix='fa')
            ).add_to(m)
        
        # 绘制B点
        if st.session_state.b_point["set"]:
            folium.Marker(
                location=[st.session_state.b_point["lat"], st.session_state.b_point["lon"]],
                popup=f"终点B\n{st.session_state.b_point['lat']:.4f}, {st.session_state.b_point['lon']:.4f}",
                icon=folium.Icon(color="green", icon="flag-checkered", prefix='fa')
            ).add_to(m)
            
            # 绘制A-B航线（考虑障碍物避障）
            if st.session_state.a_point["set"]:
                # 简单直线航线
                folium.PolyLine(
                    locations=[
                        [st.session_state.a_point["lat"], st.session_state.a_point["lon"]],
                        [st.session_state.b_point["lat"], st.session_state.b_point["lon"]]
                    ],
                    color="blue",
                    weight=3,
                    opacity=0.6,
                    dash_array='5, 5'
                ).add_to(m)
        
        # 绘制所有障碍物多边形
        for idx, obstacle in enumerate(st.session_state.obstacles):
            if len(obstacle) >= 3:
                # 绘制填充多边形
                folium.Polygon(
                    locations=obstacle,
                    color="red",
                    weight=2,
                    fill=True,
                    fill_color="red",
                    fill_opacity=0.4,
                    popup=f"障碍物 {idx+1}"
                ).add_to(m)
                
                # 绘制边界线
                folium.PolyLine(
                    locations=obstacle + [obstacle[0]],  # 闭合多边形
                    color="darkred",
                    weight=3,
                    opacity=0.8
                ).add_to(m)
        
        # 绘制正在绘制的多边形
        if st.session_state.drawing_polygon and len(st.session_state.current_polygon) > 0:
            folium.PolyLine(
                locations=st.session_state.current_polygon,
                color="orange",
                weight=3,
                opacity=0.8
            ).add_to(m)
            
            # 绘制临时点
            for point in st.session_state.current_polygon:
                folium.CircleMarker(
                    location=point,
                    radius=5,
                    color="orange",
                    fill=True
                ).add_to(m)
        
        # 使用 st_folium 获取交互
        map_data = st_folium(m, width="100%", height=600, key="route_map")
        
        # 处理地图点击事件（多边形绘制）
        if map_data and map_data.get("last_clicked"):
            if st.session_state.drawing_polygon:
                clicked_lat = map_data["last_clicked"]["lat"]
                clicked_lon = map_data["last_clicked"]["lng"]
                st.session_state.current_polygon.append([clicked_lat, clicked_lon])
                st.rerun()
    
    # 控制面板
    with col_ctrl:
        st.subheader("⚙️ 控制面板")
        
        # A点设置
        with st.expander("📍 起点A", expanded=True):
            a_lat = st.number_input("A点纬度", value=st.session_state.a_point["lat"], 
                                    min_value=-90.0, max_value=90.0, step=0.0001, format="%.4f", key="a_lat")
            a_lon = st.number_input("A点经度", value=st.session_state.a_point["lon"], 
                                    min_value=-180.0, max_value=180.0, step=0.0001, format="%.4f", key="a_lon")
            if st.button("✅ 设置A点", use_container_width=True):
                st.session_state.a_point = {"lat": a_lat, "lon": a_lon, "set": True}
                st.success("A点已设置")
                st.rerun()
        
        # B点设置
        with st.expander("📍 终点B", expanded=True):
            b_lat = st.number_input("B点纬度", value=st.session_state.b_point["lat"], 
                                    min_value=-90.0, max_value=90.0, step=0.0001, format="%.4f", key="b_lat")
            b_lon = st.number_input("B点经度", value=st.session_state.b_point["lon"], 
                                    min_value=-180.0, max_value=180.0, step=0.0001, format="%.4f", key="b_lon")
            if st.button("✅ 设置B点", use_container_width=True):
                st.session_state.b_point = {"lat": b_lat, "lon": b_lon, "set": True}
                st.success("B点已设置")
                st.rerun()
        
        # 飞行参数
        with st.expander("📊 飞行参数", expanded=True):
            st.session_state.flight_height = st.number_input("设定飞行高度(m)", 
                                                              value=st.session_state.flight_height,
                                                              min_value=5.0, max_value=500.0, step=1.0)
            st.info(f"当前航线高度: {st.session_state.flight_height}m")
        
        st.divider()
        
        # 障碍物管理
        st.subheader("🚧 障碍物管理")
        
        # 绘制控制
        col_draw1, col_draw2 = st.columns(2)
        with col_draw1:
            if not st.session_state.drawing_polygon:
                if st.button("✏️ 开始绘制", use_container_width=True):
                    st.session_state.drawing_polygon = True
                    st.session_state.current_polygon = []
                    st.rerun()
            else:
                if st.button("🔄 取消绘制", use_container_width=True):
                    st.session_state.drawing_polygon = False
                    st.session_state.current_polygon = []
                    st.rerun()
        
        with col_draw2:
            if st.session_state.drawing_polygon and len(st.session_state.current_polygon) >= 3:
                if st.button("✅ 完成绘制", use_container_width=True):
                    # 保存多边形（需要闭合）
                    polygon = st.session_state.current_polygon
                    if polygon[0] != polygon[-1]:
                        polygon.append(polygon[0])
                    st.session_state.obstacles.append(polygon)
                    st.session_state.drawing_polygon = False
                    st.session_state.current_polygon = []
                    st.success("障碍物已添加")
                    st.rerun()
        
        # 障碍物列表
        if st.session_state.obstacles:
            st.write(f"**当前障碍物 ({len(st.session_state.obstacles)}个)**")
            for idx, obs in enumerate(st.session_state.obstacles):
                col_obs1, col_obs2 = st.columns([3, 1])
                with col_obs1:
                    st.write(f"障碍物 {idx+1}: {len(obs)}个顶点")
                with col_obs2:
                    if st.button(f"🗑️", key=f"del_{idx}"):
                        st.session_state.obstacles.pop(idx)
                        st.rerun()
        else:
            st.info("暂无障碍物，点击「开始绘制」添加")
        
        st.divider()
        
        # 持久化操作
        st.subheader("💾 障碍物配置持久化")
        st.caption(f"配置文件: {os.path.abspath(CONFIG_FILE)}")
        
        col_save, col_load = st.columns(2)
        with col_save:
            if st.button("💾 保存到文件", use_container_width=True):
                save_time = save_obstacles(st.session_state.obstacles)
                st.session_state.obstacle_save_time = save_time
                st.success(f"已保存 {len(st.session_state.obstacles)} 个障碍物")
        
        with col_load:
            if st.button("📂 从文件加载", use_container_width=True):
                obstacles, save_time = load_obstacles()
                if obstacles:
                    st.session_state.obstacles = obstacles
                    st.session_state.obstacle_save_time = save_time
                    st.success(f"已加载 {len(obstacles)} 个障碍物")
                else:
                    st.warning("没有找到保存的配置文件")
        
        col_clear, col_deploy = st.columns(2)
        with col_clear:
            if st.button("🗑️ 清除全部", use_container_width=True):
                st.session_state.obstacles = []
                st.session_state.obstacle_save_time = ''
                st.success("已清除所有障碍物")
                st.rerun()
        
        with col_deploy:
            if st.button("🚀 一键部署", use_container_width=True, type="primary"):
                save_obstacles(st.session_state.obstacles)
                st.success("配置已部署到飞行系统")
        
        # 显示保存状态
        if st.session_state.obstacle_save_time:
            st.caption(f"📅 上次保存: {st.session_state.obstacle_save_time}")
        
        st.divider()
        
        # 下载配置文件
        st.subheader("📥 下载配置文件")
        config_data = {
            'obstacles': st.session_state.obstacles,
            'version': 'v12.2',
            'export_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        json_str = json.dumps(config_data, ensure_ascii=False, indent=2)
        st.download_button(
            label="📥 下载 obstacle_config.json",
            data=json_str,
            file_name="obstacle_config.json",
            mime="application/json",
            use_container_width=True
        )

# -------------------------- 页面2：飞行监控 --------------------------
elif st.session_state.current_page == "飞行监控":
    st.header("📡 无人机飞行监控系统")
    
    # 分栏布局
    col_map, col_data = st.columns([2, 1])
    
    # 地图区域
    with col_map:
        st.subheader("🗺️ 实时飞行轨迹")
        
        # 底图配置
        if coord_system == "GCJ-02 (高德/百度)":
            tile_url = "https://webst01.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}"
            tile_attr = "&copy; 高德地图"
        else:
            tile_url = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            tile_attr = "&copy; OpenStreetMap"
        
        latest = st.session_state.flight_data.iloc[-1]
        m = folium.Map(
            location=[latest["纬度"], latest["经度"]],
            zoom_start=18,
            tiles=tile_url,
            attr=tile_attr,
            control_scale=True
        )
        
        # 绘制历史轨迹
        if len(st.session_state.flight_data) > 1:
            folium.PolyLine(
                locations=st.session_state.flight_data[["纬度", "经度"]].values.tolist(),
                color="blue",
                weight=2,
                opacity=0.6
            ).add_to(m)
        
        # 绘制障碍物
        for idx, obstacle in enumerate(st.session_state.obstacles):
            if len(obstacle) >= 3:
                folium.Polygon(
                    locations=obstacle,
                    color="red",
                    weight=2,
                    fill=True,
                    fill_color="red",
                    fill_opacity=0.4,
                    popup=f"障碍物 {idx+1}"
                ).add_to(m)
        
        # 绘制A/B点
        if st.session_state.a_point["set"]:
            folium.Marker(
                location=[st.session_state.a_point["lat"], st.session_state.a_point["lon"]],
                popup="起点A",
                icon=folium.Icon(color="red", icon="play", prefix='fa')
            ).add_to(m)
        
        if st.session_state.b_point["set"]:
            folium.Marker(
                location=[st.session_state.b_point["lat"], st.session_state.b_point["lon"]],
                popup="终点B",
                icon=folium.Icon(color="green", icon="flag-checkered", prefix='fa')
            ).add_to(m)
        
        # 当前无人机位置
        folium.Marker(
            location=[latest["纬度"], latest["经度"]],
            popup=f"无人机位置\n高度: {latest['高度(m)']}m\n速度: {latest['速度(m/s)']}m/s",
            icon=folium.Icon(color="darkblue", icon="camera", prefix='fa')
        ).add_to(m)
        
        st_folium(m, width="100%", height=500, key="flight_map")
        
        # 控制按钮
        col_start, col_stop, col_update = st.columns(3)
        with col_start:
            if st.button("▶️ 开始任务", use_container_width=True):
                if st.session_state.a_point["set"] and st.session_state.b_point["set"]:
                    st.success("任务已启动，无人机正在飞往目标点")
                    # 初始化飞行数据
                    st.session_state.flight_data = pd.DataFrame({
                        "时间": [datetime.now().strftime("%H:%M:%S")],
                        "纬度": [st.session_state.a_point["lat"]],
                        "经度": [st.session_state.a_point["lon"]],
                        "高度(m)": [st.session_state.flight_height],
                        "速度(m/s)": [5.0],
                        "电量(%)": [100],
                        "状态": ["飞行中"]
                    })
                    st.rerun()
                else:
                    st.error("请先在航线规划页面设置A点和B点")
        
        with col_stop:
            if st.button("⏹️ 紧急悬停", use_container_width=True):
                st.warning("无人机已悬停")
                new_row = st.session_state.flight_data.iloc[-1].to_dict()
                new_row["时间"] = datetime.now().strftime("%H:%M:%S")
                new_row["状态"] = "悬停中"
                st.session_state.flight_data = pd.concat([st.session_state.flight_data, pd.DataFrame([new_row])], ignore_index=True)
                st.rerun()
        
        with col_update:
            if st.button("🔄 模拟更新", use_container_width=True):
                latest = st.session_state.flight_data.iloc[-1]
                
                # 计算向B点移动
                if st.session_state.b_point["set"]:
                    target_lat = st.session_state.b_point["lat"]
                    target_lon = st.session_state.b_point["lon"]
                    current_lat = latest["纬度"]
                    current_lon = latest["经度"]
                    
                    # 简单的线性插值移动
                    step = 0.0003
                    new_lat = current_lat + step if current_lat < target_lat else current_lat - step if current_lat > target_lat else current_lat
                    new_lon = current_lon + step if current_lon < target_lon else current_lon - step if current_lon > target_lon else current_lon
                    
                    # 检查是否到达
                    arrived = abs(new_lat - target_lat) < 0.0001 and abs(new_lon - target_lon) < 0.0001
                    
                    new_row = {
                        "时间": datetime.now().strftime("%H:%M:%S"),
                        "纬度": new_lat,
                        "经度": new_lon,
                        "高度(m)": round(latest["高度(m)"] + random.uniform(-0.5, 0.5), 1),
                        "速度(m/s)": round(latest["速度(m/s)"] + random.uniform(-0.3, 0.3), 1),
                        "电量(%)": max(latest["电量(%)"] - 2, 0),
                        "状态": "已到达目标" if arrived else "正常飞行"
                    }
                    
                    st.session_state.flight_data = pd.concat([st.session_state.flight_data, pd.DataFrame([new_row])], ignore_index=True)
                    
                    if arrived:
                        st.success("✅ 无人机已到达目标点B！")
                    st.rerun()
    
    # 数据面板
    with col_data:
        st.subheader("📊 实时数据")
        
        latest = st.session_state.flight_data.iloc[-1]
        
        # 指标卡片
        col1, col2 = st.columns(2)
        with col1:
            st.metric("📏 高度", f"{latest['高度(m)']} m", delta="±0.5")
            st.metric("🔋 电量", f"{latest['电量(%)']} %", delta=f"-{2}%")
        with col2:
            st.metric("⚡ 速度", f"{latest['速度(m/s)']} m/s", delta="±0.3")
            st.metric("📍 状态", latest["状态"])
        
        st.divider()
        
        # 坐标信息
        st.subheader("📍 当前位置")
        st.write(f"纬度: {latest['纬度']:.6f}")
        st.write(f"经度: {latest['经度']:.6f}")
        st.write(f"坐标系: {coord_system}")
        
        if st.session_state.b_point["set"]:
            st.divider()
            st.subheader("🎯 目标位置")
            st.write(f"目标纬度: {st.session_state.b_point['lat']:.6f}")
            st.write(f"目标经度: {st.session_state.b_point['lon']:.6f}")
            
            # 计算剩余距离
            dist = math.sqrt((latest["纬度"] - st.session_state.b_point["lat"])**2 + 
                            (latest["经度"] - st.session_state.b_point["lon"])**2) * 111000
            st.metric("剩余距离", f"{dist:.0f} m")
        
        st.divider()
        
        # 历史数据
        st.subheader("📋 飞行日志")
        st.dataframe(st.session_state.flight_data.tail(10), use_container_width=True, hide_index=True)
        
        # 导出数据
        csv = st.session_state.flight_data.to_csv(index=False)
        st.download_button(
            label="📥 导出飞行日志",
            data=csv,
            file_name=f"flight_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True
        )
