import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
from datetime import datetime
import json
import os
from folium import plugins

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
    st.session_state.obstacles = []  # 存储多边形障碍物 [[lat, lon], ...]
if "flight_height" not in st.session_state:
    st.session_state.flight_height = 10

# -------------------------- 配置文件路径 --------------------------
CONFIG_FILE = "obstacle_config.json"

# -------------------------- 障碍物持久化函数 --------------------------
def save_obstacles_to_file():
    """保存障碍物配置到文件"""
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
        
        if set_a:
            st.session_state.a_point = {"lat": a_lat, "lon": a_lon, "set": True}
        else:
            st.session_state.a_point["set"] = False
        if set_b:
            st.session_state.b_point = {"lat": b_lat, "lon": b_lon, "set": True}
        else:
            st.session_state.b_point["set"] = False
        
        st.divider()
        
        st.subheader("🚧 障碍物配置持久化")
        st.caption(f"配置文件: {os.path.abspath(CONFIG_FILE)} | 版本: v12.2 障碍物持久化版")
        
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
                label="📥 下载配置文件",
                data=json.dumps({"obstacles": st.session_state.obstacles, "version": "v12.2"}, ensure_ascii=False, indent=2),
                file_name="obstacle_config.json",
                mime="application/json",
                use_container_width=True
            )
        
        if st.session_state.obstacles:
            st.info(f"📊 文件状态: 共 {len(st.session_state.obstacles)} 个障碍物")

    with col_map:
        st.header("🗺️ 3D校园地图")
        
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
        
        # 绘制已保存的障碍物
        for i, obstacle in enumerate(st.session_state.obstacles):
            folium.Polygon(
                locations=obstacle,
                color="red",
                weight=2,
                fill=True,
                fill_color="red",
                fill_opacity=0.3,
                popup=f"障碍物 {i+1}"
            ).add_to(m)
        
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
            if st.session_state.a_point["set"]:
                folium.PolyLine(
                    locations=[
                        [st.session_state.a_point["lat"], st.session_state.a_point["lon"]],
                        [st.session_state.b_point["lat"], st.session_state.b_point["lon"]]
                    ],
                    color="blue",
                    weight=3,
                    opacity=0.8,
                    popup=f"航线 (高: {st.session_state.flight_height}m)"
                ).add_to(m)
        
        # 渲染地图并获取绘制的数据
        output = st_folium(m, width="100%", height=600, key="route_map")
        
        # 处理新绘制的多边形
        if output and output.get("last_active_drawing"):
            drawing = output["last_active_drawing"]
            if drawing.get("geometry", {}).get("type") == "Polygon":
                coordinates = drawing["geometry"]["coordinates"][0]
                # 转换坐标格式 [[lng, lat], ...] -> [[lat, lng], ...]
                polygon_coords = [[coord[1], coord[0]] for coord in coordinates]
                st.session_state.obstacles.append(polygon_coords)
                st.success(f"✅ 已添加障碍物，当前共 {len(st.session_state.obstacles)} 个")
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
                locations=obstacle,
                color="red",
                weight=2,
                fill=True,
                fill_color="red",
                fill_opacity=0.3,
                popup=f"障碍物 {i+1}"
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
        
        folium.Marker(
            location=[latest["纬度"], latest["经度"]],
            popup=f"当前位置\n高度: {latest['高度(m)']}m\n速度: {latest['速度(m/s)']}m/s",
            icon=folium.Icon(color="red", icon="plane", prefix='fa')
        ).add_to(m)
        
        st_folium(m, width="100%", height=500, key="flight_map")
        
        if st.button("🔄 更新飞行数据", use_container_width=True):
            new_row = {
                "时间": datetime.now().strftime("%H:%M:%S"),
                "纬度": latest["纬度"] + 0.0001,
                "经度": latest["经度"] + 0.0001,
                "高度(m)": round(latest["高度(m)"] + 0.2, 1),
                "速度(m/s)": round(latest["速度(m/s)"] + 0.1, 1),
                "电量(%)": max(latest["电量(%)"] - 1, 0),
                "状态": "正常飞行" if latest["电量(%)"] > 20 else "低电量告警"
            }
            st.session_state.flight_data = pd.concat([st.session_state.flight_data, pd.DataFrame([new_row])], ignore_index=True)
            st.rerun()
    
    with col_data:
        st.subheader("📊 实时参数")
        latest = st.session_state.flight_data.iloc[-1]
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric(label="📏 高度(m)", value=latest["高度(m)"])
            st.metric(label="🔋 电量(%)", value=latest["电量(%)"])
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
                st.write(f"障碍物 {i+1}: {len(obs)} 个顶点")
        
        st.divider()
        st.subheader("📋 飞行历史")
        st.dataframe(st.session_state.flight_data.tail(10), use_container_width=True, hide_index=True)
