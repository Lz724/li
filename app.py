import streamlit as st
import folium
from streamlit_folium import st_folium
import json
import os
import math
from folium import plugins

# 页面配置
st.set_page_config(page_title="无人机航线规划", layout="wide")

# 状态初始化
if "a" not in st.session_state:
    st.session_state.a = {"lat": 32.2323, "lon": 118.749, "set": False}
if "b" not in st.session_state:
    st.session_state.b = {"lat": 32.2344, "lon": 118.749, "set": False}
if "obstacles" not in st.session_state:
    st.session_state.obstacles = []  # [{"polygon":[[lat,lng],...], "height":10}]
if "flight_h" not in st.session_state:
    st.session_state.flight_h = 10
if "safe_r" not in st.session_state:
    st.session_state.safe_r = 5

# 保存障碍物
def save_obs():
    with open("obs.json", "w") as f:
        json.dump(st.session_state.obstacles, f)

def load_obs():
    if os.path.exists("obs.json"):
        with open("obs.json") as f:
            st.session_state.obstacles = json.load(f)
        st.rerun()

# 简单绕行算法
def plan_route():
    if not st.session_state.a["set"] or not st.session_state.b["set"]:
        return []
    
    start = (st.session_state.a["lat"], st.session_state.a["lon"])
    end = (st.session_state.b["lat"], st.session_state.b["lon"])
    
    # 检查是否需要绕行
    need_bypass = []
    for obs in st.session_state.obstacles:
        # 简单判断航线是否经过障碍物区域
        if st.session_state.flight_h <= obs.get("height", 0):
            need_bypass.append(obs)
    
    if not need_bypass:
        return [start, end]
    
    # 绕行策略：向左/向右/最佳
    strategy = st.session_state.get("strategy", "最佳航线")
    waypoints = [start]
    
    for obs in need_bypass:
        # 计算障碍物中心
        poly = obs["polygon"]
        center = (sum(p[0] for p in poly)/len(poly), sum(p[1] for p in poly)/len(poly))
        
        # 航线方向向量
        dx, dy = end[1]-start[1], end[0]-start[0]
        length = math.hypot(dx, dy)
        if length > 0:
            perp = (-dy/length, dx/length) if strategy == "向左绕行" else (dy/length, -dx/length)
        else:
            perp = (0, 1)
        
        offset = st.session_state.safe_r / 111000  # 米转纬度
        bypass = (center[0] + perp[0]*offset, center[1] + perp[1]*offset)
        waypoints.append(bypass)
    
    waypoints.append(end)
    return waypoints

# 界面
col1, col2 = st.columns([1, 2])

with col1:
    st.header("控制面板")
    
    # 起终点
    st.subheader("起点A")
    a_lat = st.number_input("纬度", value=st.session_state.a["lat"], step=0.0001, format="%.4f")
    a_lon = st.number_input("经度", value=st.session_state.a["lon"], step=0.0001, format="%.4f")
    if st.button("设置A点"):
        st.session_state.a = {"lat": a_lat, "lon": a_lon, "set": True}
        st.rerun()
    
    st.subheader("终点B")
    b_lat = st.number_input("纬度", value=st.session_state.b["lat"], step=0.0001, format="%.4f")
    b_lon = st.number_input("经度", value=st.session_state.b["lon"], step=0.0001, format="%.4f")
    if st.button("设置B点"):
        st.session_state.b = {"lat": b_lat, "lon": b_lon, "set": True}
        st.rerun()
    
    # 飞行参数
    st.subheader("飞行参数")
    st.session_state.flight_h = st.number_input("飞行高度(m)", value=st.session_state.flight_h, min_value=5)
    st.session_state.safe_r = st.number_input("安全半径(m)", value=st.session_state.safe_r, min_value=1)
    
    st.subheader("绕行策略")
    strategy = st.selectbox("策略", ["向左绕行", "向右绕行", "最佳航线"])
    st.session_state.strategy = strategy
    
    if st.button("规划航线", type="primary"):
        route = plan_route()
        st.session_state.route = route
        if route:
            st.success(f"规划完成，共{len(route)}个航点")
    
    # 障碍物管理
    st.subheader("障碍物")
    for i, obs in enumerate(st.session_state.obstacles):
        h = st.number_input(f"障碍物{i+1}高度(m)", value=obs.get("height", 10), key=f"h{i}")
        st.session_state.obstacles[i]["height"] = h
    
    if st.button("保存配置"):
        save_obs()
    if st.button("加载配置"):
        load_obs()
    if st.button("清除所有"):
        st.session_state.obstacles = []
        st.rerun()

with col2:
    st.header("地图 (多边形圈选障碍物)")
    
    # 地图
    center = (st.session_state.a["lat"], st.session_state.a["lon"]) if st.session_state.a["set"] else (32.2323, 118.749)
    m = folium.Map(location=center, zoom_start=18)
    
    # 绘制控件
    plugins.Draw(
        draw_options={'polygon': {'allowIntersection': False}, 'polyline': False, 'rectangle': False, 'circle': False, 'marker': False},
        edit_options={'edit': True, 'remove': True}
    ).add_to(m)
    
    # 绘制障碍物
    for i, obs in enumerate(st.session_state.obstacles):
        folium.Polygon(obs["polygon"], color="red", fill=True, fill_opacity=0.3, popup=f"高:{obs.get('height',0)}m").add_to(m)
    
    # 绘制起终点
    if st.session_state.a["set"]:
        folium.Marker([st.session_state.a["lat"], st.session_state.a["lon"]], popup="A", icon=folium.Icon(color="green")).add_to(m)
    if st.session_state.b["set"]:
        folium.Marker([st.session_state.b["lat"], st.session_state.b["lon"]], popup="B", icon=folium.Icon(color="blue")).add_to(m)
    
    # 绘制航线
    if "route" in st.session_state and st.session_state.route:
        folium.PolyLine(st.session_state.route, color="green", weight=3).add_to(m)
    
    # 获取绘制的多边形
    output = st_folium(m, width=800, height=600)
    if output and output.get("last_active_drawing"):
        drawing = output["last_active_drawing"]
        if drawing.get("geometry", {}).get("type") == "Polygon":
            coords = drawing["geometry"]["coordinates"][0]
            polygon = [[c[1], c[0]] for c in coords]
            st.session_state.obstacles.append({"polygon": polygon, "height": 10})
            st.success("已添加障碍物")
            st.rerun()
