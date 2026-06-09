import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import json
import os
import math
import random
from datetime import datetime
from folium import plugins

# ---------------------------- 页面配置 ----------------------------
st.set_page_config(page_title="无人机智能规划", layout="wide")

# ---------------------------- 初始化状态 ----------------------------
if "a" not in st.session_state:
    st.session_state.a = {"lat": 32.2323, "lon": 118.749, "set": False}
if "b" not in st.session_state:
    st.session_state.b = {"lat": 32.2344, "lon": 118.749, "set": False}
if "obstacles" not in st.session_state:
    st.session_state.obstacles = []          # [{"polygon":[[lat,lon],...], "height":10}]
if "flight_h" not in st.session_state:
    st.session_state.flight_h = 50
if "safe_r" not in st.session_state:
    st.session_state.safe_r = 5
if "bypass" not in st.session_state:
    st.session_state.bypass = "最佳航线"
if "route" not in st.session_state:
    st.session_state.route = []               # 规划出的航线点 [[lat,lon],...]
if "flight_log" not in st.session_state:
    st.session_state.flight_log = pd.DataFrame(columns=["时间","纬度","经度","高度","速度","电量","状态"])
    st.session_state.flight_log.loc[0] = [datetime.now().strftime("%H:%M:%S"), 32.23335, 118.749, 50, 3.2, 85, "正常"]

# ---------------------------- 障碍物持久化 ----------------------------
CONFIG_FILE = "obstacle_config.json"

def save_obstacles():
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(st.session_state.obstacles, f, ensure_ascii=False, indent=2)
    st.success(f"已保存 {len(st.session_state.obstacles)} 个障碍物")

def load_obstacles():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            st.session_state.obstacles = json.load(f)
        st.success(f"已加载 {len(st.session_state.obstacles)} 个障碍物")
        st.rerun()

def clear_obstacles():
    st.session_state.obstacles = []
    st.session_state.route = []
    st.success("已清除所有障碍物")
    st.rerun()

# ---------------------------- 航线规划算法（真实绕行）----------------------------
def point_to_line_distance(p, a, b):
    """点到线段距离（经纬度近似平面）"""
    x0, y0 = p
    x1, y1 = a
    x2, y2 = b
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x0 - x1, y0 - y1)
    t = ((x0 - x1) * dx + (y0 - y1) * dy) / (dx*dx + dy*dy)
    if t < 0:
        return math.hypot(x0 - x1, y0 - y1)
    elif t > 1:
        return math.hypot(x0 - x2, y0 - y2)
    else:
        proj = (x1 + t*dx, y1 + t*dy)
        return math.hypot(x0 - proj[0], y0 - proj[1])

def plan_route():
    if not st.session_state.a["set"] or not st.session_state.b["set"]:
        st.warning("请先设置起点A和终点B")
        return []
    A = (st.session_state.a["lat"], st.session_state.a["lon"])
    B = (st.session_state.b["lat"], st.session_state.b["lon"])
    flight_h = st.session_state.flight_h
    safe_r = st.session_state.safe_r
    strategy = st.session_state.bypass

    # 筛选需要绕行的障碍物（高度 >= 飞行高度 且 与航线相交）
    need_bypass = []
    for obs in st.session_state.obstacles:
        if obs.get("height", 0) >= flight_h:
            # 粗略判断多边形与线段是否相交
            poly = obs["polygon"]
            # 检查线段是否与多边形任一边相交
            intersect = False
            for i in range(len(poly)):
                p1 = poly[i]
                p2 = poly[(i+1)%len(poly)]
                # 计算交点
                if line_segments_cross(A, B, p1, p2):
                    intersect = True
                    break
            # 或者起点/终点在多边形内部
            if point_in_polygon(A, poly) or point_in_polygon(B, poly):
                intersect = True
            if intersect:
                need_bypass.append(obs)

    if not need_bypass:
        # 全部飞跃
        return [A, B]

    # 有需要绕行的障碍物 -> 生成绕行点
    waypoints = [A]
    current_pos = A
    # 按距离起点排序障碍物（沿航线方向）
    def dist_along(p):
        # 投影到AB线段上的参数t
        dx, dy = B[0]-A[0], B[1]-A[1]
        if dx==0 and dy==0:
            return 0
        t = ((p[0]-A[0])*dx + (p[1]-A[1])*dy) / (dx*dx+dy*dy)
        return t
    need_bypass.sort(key=lambda x: dist_along(get_polygon_center(x["polygon"])))

    for obs in need_bypass:
        center = get_polygon_center(obs["polygon"])
        # 绕行方向向量（垂直于AB）
        dx, dy = B[0]-A[0], B[1]-A[1]
        length = math.hypot(dx, dy)
        if length == 0:
            perp = (1, 0)
        else:
            if strategy == "向左绕行":
                perp = (-dy/length, dx/length)
            elif strategy == "向右绕行":
                perp = (dy/length, -dx/length)
            else:  # 最佳航线：分别计算左、右绕行点，选更短的
                left = (center[0] - dy/length * safe_r/111000, center[1] + dx/length * safe_r/111000)
                right = (center[0] + dy/length * safe_r/111000, center[1] - dx/length * safe_r/111000)
                # 计算哪个更接近原航线
                dist_left = point_to_line_distance(left, A, B)
                dist_right = point_to_line_distance(right, A, B)
                if dist_left < dist_right:
                    perp = (-dy/length, dx/length)
                else:
                    perp = (dy/length, -dx/length)
        # 绕行点偏移（米转度：1度≈111km）
        offset_m = safe_r + 5  # 额外5米安全距离
        offset_deg = offset_m / 111000
        bypass_point = (center[0] + perp[0] * offset_deg, center[1] + perp[1] * offset_deg)
        waypoints.append(bypass_point)
        current_pos = bypass_point

    waypoints.append(B)
    return waypoints

def line_segments_cross(p1, p2, p3, p4):
    """判断线段p1p2和p3p4是否相交"""
    def ccw(a,b,c):
        return (c[1]-a[1])*(b[0]-a[0]) - (b[1]-a[1])*(c[0]-a[0])
    d1 = ccw(p3,p4,p1)
    d2 = ccw(p3,p4,p2)
    d3 = ccw(p1,p2,p3)
    d4 = ccw(p1,p2,p4)
    if ((d1>0 and d2<0) or (d1<0 and d2>0)) and ((d3>0 and d4<0) or (d3<0 and d4>0)):
        return True
    return False

def point_in_polygon(point, poly):
    """射线法判断点是否在多边形内"""
    x, y = point
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i+1)%n]
        if ((y1 > y) != (y2 > y)) and (x < (x2-x1)*(y-y1)/(y2-y1) + x1):
            inside = not inside
    return inside

def get_polygon_center(poly):
    lat = sum(p[0] for p in poly)/len(poly)
    lon = sum(p[1] for p in poly)/len(poly)
    return (lat, lon)

# ---------------------------- 心跳包模拟 ----------------------------
def heartbeat():
    """模拟无人机心跳，沿规划航线移动"""
    if len(st.session_state.route) < 2:
        # 无航线时随机游走
        last = st.session_state.flight_log.iloc[-1]
        new_lat = last["纬度"] + random.uniform(-0.0001, 0.0001)
        new_lon = last["经度"] + random.uniform(-0.0001, 0.0001)
        new_h = max(0, last["高度"] + random.uniform(-0.5, 0.5))
        new_speed = max(0, last["速度"] + random.uniform(-0.2, 0.2))
    else:
        # 沿航线移动
        last = st.session_state.flight_log.iloc[-1]
        current = (last["纬度"], last["经度"])
        # 找到最近航点
        min_dist = float('inf')
        target_idx = 0
        for i, pt in enumerate(st.session_state.route):
            d = math.hypot(current[0]-pt[0], current[1]-pt[1])
            if d < min_dist:
                min_dist = d
                target_idx = i
        if target_idx + 1 < len(st.session_state.route):
            target = st.session_state.route[target_idx+1]
            # 向目标移动一步
            dx = target[0] - current[0]
            dy = target[1] - current[1]
            dist = math.hypot(dx, dy)
            if dist > 0:
                step = 0.00005  # 约5米
                ratio = min(1, step / dist)
                new_lat = current[0] + dx * ratio
                new_lon = current[1] + dy * ratio
            else:
                new_lat, new_lon = current
        else:
            new_lat, new_lon = current
        new_h = st.session_state.flight_h + random.uniform(-0.2, 0.2)
        new_speed = 5 + random.uniform(-0.5, 0.5)

    new_battery = max(0, st.session_state.flight_log.iloc[-1]["电量"] - random.uniform(0, 0.5))
    status = "正常" if new_battery > 20 else "低电量"
    new_row = pd.DataFrame([{
        "时间": datetime.now().strftime("%H:%M:%S"),
        "纬度": round(new_lat, 6),
        "经度": round(new_lon, 6),
        "高度": round(new_h, 1),
        "速度": round(new_speed, 1),
        "电量": round(new_battery, 1),
        "状态": status
    }])
    st.session_state.flight_log = pd.concat([st.session_state.flight_log, new_row], ignore_index=True)
    # 保留最近100条
    if len(st.session_state.flight_log) > 100:
        st.session_state.flight_log = st.session_state.flight_log.tail(100)

# ---------------------------- 界面布局 ----------------------------
tab1, tab2 = st.tabs(["🗺️ 航线规划", "📡 飞行监控"])

with tab1:
    left, right = st.columns([1, 2.5])
    with left:
        st.header("⚙️ 控制")
        # 起终点
        with st.expander("📍 起点 / 终点", expanded=True):
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                a_lat = st.number_input("A点纬度", value=st.session_state.a["lat"], step=0.0001, format="%.4f")
                a_lon = st.number_input("A点经度", value=st.session_state.a["lon"], step=0.0001, format="%.4f")
                if st.button("设置A点", use_container_width=True):
                    st.session_state.a = {"lat": a_lat, "lon": a_lon, "set": True}
                    st.rerun()
            with col_a2:
                b_lat = st.number_input("B点纬度", value=st.session_state.b["lat"], step=0.0001, format="%.4f")
                b_lon = st.number_input("B点经度", value=st.session_state.b["lon"], step=0.0001, format="%.4f")
                if st.button("设置B点", use_container_width=True):
                    st.session_state.b = {"lat": b_lat, "lon": b_lon, "set": True}
                    st.rerun()

        # 飞行参数
        with st.expander("✈️ 飞行参数", expanded=True):
            st.session_state.flight_h = st.number_input("飞行高度 (m)", value=st.session_state.flight_h, min_value=5, step=5)
            st.session_state.safe_r = st.number_input("安全半径 (m)", value=st.session_state.safe_r, min_value=1, step=1)
            st.session_state.bypass = st.selectbox("绕行策略", ["向左绕行", "向右绕行", "最佳航线"], index=["向左绕行","向右绕行","最佳航线"].index(st.session_state.bypass))
            if st.button("🚀 规划航线", type="primary", use_container_width=True):
                route = plan_route()
                if route:
                    st.session_state.route = route
                    st.success(f"规划成功！共 {len(route)} 个航点")
                else:
                    st.error("规划失败，请检查起终点和障碍物")

        # 障碍物管理
        with st.expander("🚧 障碍物管理", expanded=True):
            for i, obs in enumerate(st.session_state.obstacles):
                h = st.number_input(f"障碍物{i+1}高度 (m)", value=obs.get("height", 10), key=f"h_{i}", step=5)
                st.session_state.obstacles[i]["height"] = h
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                if st.button("💾 保存配置", use_container_width=True):
                    save_obstacles()
            with col_s2:
                if st.button("📂 加载配置", use_container_width=True):
                    load_obstacles()
            if st.button("🗑️ 清除所有障碍物", use_container_width=True):
                clear_obstacles()

    with right:
        st.header("🗺️ 地图操作：多边形圈选障碍物")
        # 地图中心
        center_lat = st.session_state.a["lat"] if st.session_state.a["set"] else 32.2323
        center_lon = st.session_state.a["lon"] if st.session_state.a["set"] else 118.749
        m = folium.Map(location=[center_lat, center_lon], zoom_start=18)
        # 绘制控件
        draw = plugins.Draw(
            draw_options={
                'polygon': {'allowIntersection': False, 'showArea': True},
                'polyline': False, 'rectangle': False, 'circle': False, 'marker': False
            },
            edit_options={'edit': True, 'remove': True}
        )
        draw.add_to(m)
        # 绘制已保存的障碍物
        for i, obs in enumerate(st.session_state.obstacles):
            folium.Polygon(
                obs["polygon"],
                color="red", weight=2, fill=True, fill_opacity=0.3,
                popup=f"障碍物{i+1} 高:{obs.get('height',10)}m"
            ).add_to(m)
        # 绘制A/B点
        if st.session_state.a["set"]:
            folium.Marker([st.session_state.a["lat"], st.session_state.a["lon"]], popup="起点A", icon=folium.Icon(color="green")).add_to(m)
        if st.session_state.b["set"]:
            folium.Marker([st.session_state.b["lat"], st.session_state.b["lon"]], popup="终点B", icon=folium.Icon(color="blue")).add_to(m)
        # 绘制规划航线
        if st.session_state.route:
            folium.PolyLine(st.session_state.route, color="green", weight=4, opacity=0.8, popup="规划航线").add_to(m)
            for pt in st.session_state.route:
                folium.CircleMarker(pt, radius=3, color="green", fill=True).add_to(m)

        output = st_folium(m, width=700, height=550)
        # 处理新绘制的多边形
        if output and output.get("last_active_drawing"):
            draw_data = output["last_active_drawing"]
            if draw_data.get("geometry", {}).get("type") == "Polygon":
                coords = draw_data["geometry"]["coordinates"][0]
                polygon_latlng = [[c[1], c[0]] for c in coords]
                st.session_state.obstacles.append({"polygon": polygon_latlng, "height": 10})
                st.success("已添加新障碍物，默认高度10米，请在左侧修改高度")
                st.rerun()

with tab2:
    st.header("📡 飞行监控")
    col_map, col_info = st.columns([2, 1])
    with col_map:
        # 实时地图
        last = st.session_state.flight_log.iloc[-1]
        m2 = folium.Map(location=[last["纬度"], last["经度"]], zoom_start=18)
        # 障碍物
        for i, obs in enumerate(st.session_state.obstacles):
            folium.Polygon(obs["polygon"], color="red", fill=True, fill_opacity=0.2, popup=f"高:{obs['height']}m").add_to(m2)
        # 历史轨迹
        track = st.session_state.flight_log[["纬度", "经度"]].values.tolist()
        if len(track) > 1:
            folium.PolyLine(track, color="blue", weight=2, opacity=0.5).add_to(m2)
        # 规划航线
        if st.session_state.route:
            folium.PolyLine(st.session_state.route, color="green", weight=3, dash_array='5,5', popup="规划线").add_to(m2)
        # 当前位置
        folium.Marker([last["纬度"], last["经度"]], popup=f"高度:{last['高度']}m 速度:{last['速度']}m/s", icon=folium.Icon(color="red", icon="plane")).add_to(m2)
        st_folium(m2, width=600, height=500)
        # 心跳控制
        if st.button("🔄 模拟心跳包 (更新位置)", use_container_width=True):
            heartbeat()
            st.rerun()
        auto = st.checkbox("自动刷新 (每2秒)")
        if auto:
            import time
            time.sleep(2)
            heartbeat()
            st.rerun()
    with col_info:
        st.subheader("📊 实时数据")
        st.metric("高度 (m)", f"{last['高度']:.1f}")
        st.metric("速度 (m/s)", f"{last['速度']:.1f}")
        st.metric("电量 (%)", f"{last['电量']:.0f}")
        st.metric("状态", last["状态"])
        st.divider()
        st.subheader("📋 飞行记录")
        st.dataframe(st.session_state.flight_log.tail(10), use_container_width=True, hide_index=True)
