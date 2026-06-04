import streamlit as st
import pandas as pd
import time
import math
from datetime import datetime
import folium
from streamlit_folium import folium_static
from geopy.distance import geodesic

# ---------------------------- 坐标系GCJ02/WGS84转换 ----------------------------
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

def convert_coords(lat, lng, from_system, to_system="WGS-84"):
    if from_system == to_system:
        return lng, lat
    if from_system == "WGS-84" and to_system == "GCJ-02":
        return wgs84_to_gcj02(lng, lat)
    if from_system == "GCJ-02" and to_system == "WGS-84":
        return gcj02_to_wgs84(lng, lat)
    return lng, lat

# ---------------------------- 初始化缓存参数 ----------------------------
def init_state():
    if "running" not in st.session_state:
        st.session_state.running = False
        st.session_state.seq = 0
        st.session_state.last_ts = None
        st.session_state.records = []
        st.session_state.alert_msg = ""
    if "coord_system" not in st.session_state:
        st.session_state.coord_system = "GCJ-02"
    if "point_A" not in st.session_state:
        st.session_state.point_A = {"lat": 32.2322, "lng": 118.749, "set": False}
    if "point_B" not in st.session_state:
        st.session_state.point_B = {"lat": 32.2343, "lng": 118.749, "set": False}
    if "flight_height" not in st.session_state:
        st.session_state.flight_height = 50.0
    if "obstacles" not in st.session_state:
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

# ---------------------------- 生成Folium地图函数 ----------------------------
def create_folium_map():
    if st.session_state.point_A["set"]:
        center_lat = st.session_state.point_A["lat"]
        center_lng = st.session_state.point_A["lng"]
    elif st.session_state.point_B["set"]:
        center_lat = st.session_state.point_B["lat"]
        center_lng = st.session_state.point_B["lng"]
    else:
        center_lat = 32.2332
        center_lng = 118.7492

    m = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=st.session_state.map_zoom,
        control_scale=True,
        tiles='OpenStreetMap'
    )
    folium.TileLayer('CartoDB positron', name='浅色地图').add_to(m)
    folium.TileLayer('CartoDB dark_matter', name='深色地图').add_to(m)

    # A起点
    if st.session_state.point_A["set"]:
        folium.Marker(
            [st.session_state.point_A["lat"], st.session_state.point_A["lng"]],
            popup="起点A", icon=folium.Icon(color="green", icon="play", prefix="fa")
        ).add_to(m)
        folium.Circle([st.session_state.point_A["lat"], st.session_state.point_A["lng"]], radius=20, color="green", fill=True, fill_opacity=0.2).add_to(m)
    # B终点
    if st.session_state.point_B["set"]:
        folium.Marker(
            [st.session_state.point_B["lat"], st.session_state.point_B["lng"]],
            popup="终点B", icon=folium.Icon(color="red", icon="flag-checkered", prefix="fa")
        ).add_to(m)
        folium.Circle([st.session_state.point_B["lat"], st.session_state.point_B["lng"]], radius=20, color="red", fill=True, fill_opacity=0.2).add_to(m)
    # AB航线
    if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
        line_points = [[st.session_state.point_A["lat"], st.session_state.point_A["lng"]],
                       [st.session_state.point_B["lat"], st.session_state.point_B["lng"]]]
        folium.PolyLine(line_points, color="yellow", weight=5, opacity=0.8).add_to(m)
    # 障碍物
    for obs in st.session_state.obstacles:
        folium.Circle(
            location=[obs["lat"], obs["lng"]], radius=obs["radius"],
            color="red", fill=True, fill_opacity=0.4, popup=obs["name"]
        ).add_to(m)
    return m

# ---------------------------- 页面主体 ----------------------------
st.set_page_config(page_title="无人机地面站系统", layout="wide")
st.sidebar.title("功能导航")
page = st.sidebar.radio("选择页面", ["航线规划", "飞行心跳监控"])

# ========== 航线规划页面 ==========
if page == "航线规划":
    st.title("🗺️ 无人机航线规划系统")
    col_left, col_right = st.columns([1,2])
    with col_left:
        st.subheader("点位与参数设置")
        # A点设置
        st.markdown("#### 起点A")
        a_lat = st.number_input("A纬度", value=st.session_state.point_A["lat"], format="%.6f")
        a_lng = st.number_input("A经度", value=st.session_state.point_A["lng"], format="%.6f")
        if st.button("📍确认设置A点"):
            st.session_state.point_A = {"lat":a_lat,"lng":a_lng,"set":True}
            st.rerun()
        # B点设置
        st.markdown("#### 终点B")
        b_lat = st.number_input("B纬度", value=st.session_state.point_B["lat"], format="%.6f")
        b_lng = st.number_input("B经度", value=st.session_state.point_B["lng"], format="%.6f")
        if st.button("🎯确认设置B点"):
            st.session_state.point_B = {"lat":b_lat,"lng":b_lng,"set":True}
            st.rerun()
        # 飞行高度
        st.session_state.flight_height = st.number_input("飞行高度(m)", value=st.session_state.flight_height, step=5.0)
        # 新增障碍物
        st.markdown("#### 添加障碍物")
        obs_name = st.text_input("障碍物名称", value="新障碍物")
        o_lat = st.number_input("障碍物纬度", value=32.2330, format="%.6f")
        o_lng = st.number_input("障碍物经度", value=118.7495, format="%.6f")
        o_radius = st.number_input("防护半径(m)", value=25)
        if st.button("✅新增障碍物"):
            st.session_state.obstacles.append({"lat":o_lat,"lng":o_lng,"radius":o_radius,"name":obs_name})
            st.rerun()

    with col_right:
        st.subheader("地图预览")
        map_data = create_folium_map()
        folium_static(map_data, width=1100, height=620)
        # 航线距离计算
        if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
            dist_m = geodesic((a_lat,a_lng),(b_lat,b_lng)).meters
            st.success(f"✅ 航线直线距离：{dist_m:.2f} 米")

# ========== 心跳监控页面 ==========
else:
    st.title("🛸 无人机心跳实时监控")
    c1,c2,c3 = st.columns(3)
    with c1:
        if st.button("🚀启动模拟"):
            reset_monitor()
            st.session_state.running = True
    with c2:
        if st.button("⏯️暂停/恢复"):
            st.session_state.running = not st.session_state.running
    with c3:
        if st.button("🛑停止重置"):
            reset_monitor()

    # 每秒生成心跳
    if st.session_state.running:
        now_t = time.time()
        last_t = st.session_state.last_ts
        if last_t is None or (now_t - last_t >= 1.0):
            new_seq = st.session_state.seq + 1
            add_heartbeat(new_seq, now_t)
        # 3秒超时告警
        gap = now_t - st.session_state.last_ts if st.session_state.last_ts else 0
        if gap>3:
            st.error(f"⚠️失联告警：{gap:.1f}秒未收到心跳包！")
        else:
            if gap>0:
                st.success(f"💓连接正常，上次心跳：{gap:.1f}s前")
    # 绘图与表格
    if len(st.session_state.records)>0:
        df_raw = pd.DataFrame(st.session_state.records, columns=["序号","时间戳"])
        df_raw["接收时刻"] = pd.to_datetime(df_raw["时间戳"], unit="s").dt.strftime("%H:%M:%S")
        st.subheader("心跳序号趋势图")
        st.line_chart(df_raw.set_index("接收时刻")["序号"])
        st.subheader("心跳明细列表")
        st.dataframe(df_raw[["序号","接收时刻"]], use_container_width=True)
    else:
        st.info("📭暂无心跳数据，请点击启动模拟")

st.divider()
st.caption("无人机地面管控系统 | WGS84/GCJ02双坐标系 | 航线规划+心跳监测")
