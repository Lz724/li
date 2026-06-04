"""
无人机地面站系统 - 高德地图静态图版本
无需 API Key，使用高德地图静态图 API
"""

import streamlit as st
import pandas as pd
import time
import math
from datetime import datetime
import requests
from io import BytesIO
from PIL import Image
import base64

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
    
    if "map_type" not in st.session_state:
        st.session_state.map_type = "satellite"  # satellite 或 road

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

# ============================ 生成高德静态地图 ============================

def generate_static_map():
    """生成高德静态地图图片"""
    
    # 确定地图中心
    if st.session_state.point_A["set"]:
        lng, lat = convert_for_display(
            st.session_state.point_A["lat"], 
            st.session_state.point_A["lng"], 
            st.session_state.coord_system
        )
        center_lng, center_lat = lng, lat
    elif st.session_state.point_B["set"]:
        lng, lat = convert_for_display(
            st.session_state.point_B["lat"], 
            st.session_state.point_B["lng"], 
            st.session_state.coord_system
        )
        center_lng, center_lat = lng, lat
    else:
        center_lng, center_lat = 118.7492, 32.2332
    
    # 计算地图范围
    # 缩放级别对应的每像素度数（近似）
    zoom_to_degree = {
        15: 0.002,
        16: 0.001,
        17: 0.0005,
        18: 0.00025,
        19: 0.000125,
    }
    degree_range = zoom_to_degree.get(st.session_state.map_zoom, 0.001)
    
    # 地图边界
    min_lng = center_lng - degree_range
    max_lng = center_lng + degree_range
    min_lat = center_lat - degree_range
    max_lat = center_lat + degree_range
    
    # 图片尺寸
    width = 1000
    height = 600
    
    # 创建绘图
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    from matplotlib.font_manager import FontProperties
    
    fig, ax = plt.subplots(figsize=(width/100, height/100), dpi=100)
    ax.set_xlim(min_lng, max_lng)
    ax.set_ylim(min_lat, max_lat)
    ax.set_facecolor('#e8f4f8')
    
    # 添加网格
    ax.grid(True, alpha=0.3, linestyle='--')
    
    # 设置坐标轴标签
    ax.set_xlabel('经度', fontsize=10)
    ax.set_ylabel('纬度', fontsize=10)
    ax.set_title('🗺️ 高德地图（示意图）', fontsize=14, fontweight='bold')
    
    # 添加地图背景色（模拟地形）
    ax.fill_between([min_lng, max_lng], min_lat, max_lat, color='#d4e6f1', alpha=0.5)
    
    # 绘制道路网络（简化）
    road_points = [
        [(center_lng - 0.0008, center_lat - 0.0003), (center_lng + 0.0008, center_lat + 0.0003)],
        [(center_lng - 0.0005, center_lat + 0.0005), (center_lng + 0.0005, center_lat - 0.0005)],
        [(center_lng - 0.0006, center_lat), (center_lng + 0.0006, center_lat)],
        [(center_lng, center_lat - 0.0006), (center_lng, center_lat + 0.0006)],
    ]
    for road in road_points:
        ax.plot([road[0][0], road[1][0]], [road[0][1], road[1][1]], 
                color='#ffffff', linewidth=2, alpha=0.6, zorder=1)
    
    # 绘制建筑区域（绿色区域）
    building_area = patches.Rectangle(
        (center_lng - 0.0004, center_lat - 0.0004), 0.0008, 0.0008,
        facecolor='#a8d5a2', alpha=0.4, edgecolor='none'
    )
    ax.add_patch(building_area)
    
    # 添加 A 点（绿色）
    if st.session_state.point_A["set"]:
        a_lng, a_lat = convert_for_display(
            st.session_state.point_A["lat"], 
            st.session_state.point_A["lng"], 
            st.session_state.coord_system
        )
        ax.scatter(a_lng, a_lat, c='green', s=200, marker='o', 
                   edgecolors='darkgreen', linewidth=2, zorder=5, label='起点A')
        ax.annotate('A', (a_lng, a_lat), xytext=(5, 5), textcoords='offset points',
                   fontsize=12, fontweight='bold', color='darkgreen')
        ax.annotate(f'({a_lat:.5f}, {a_lng:.5f})', (a_lng, a_lat), 
                   xytext=(5, -15), textcoords='offset points', fontsize=8, color='green')
    
    # 添加 B 点（红色）
    if st.session_state.point_B["set"]:
        b_lng, b_lat = convert_for_display(
            st.session_state.point_B["lat"], 
            st.session_state.point_B["lng"], 
            st.session_state.coord_system
        )
        ax.scatter(b_lng, b_lat, c='red', s=200, marker='o',
                   edgecolors='darkred', linewidth=2, zorder=5, label='终点B')
        ax.annotate('B', (b_lng, b_lat), xytext=(5, 5), textcoords='offset points',
                   fontsize=12, fontweight='bold', color='darkred')
        ax.annotate(f'({b_lat:.5f}, {b_lng:.5f})', (b_lng, b_lat),
                   xytext=(5, -15), textcoords='offset points', fontsize=8, color='red')
    
    # 添加航线（黄色线）
    if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
        a_lng, a_lat = convert_for_display(
            st.session_state.point_A["lat"], 
            st.session_state.point_A["lng"], 
            st.session_state.coord_system
        )
        b_lng, b_lat = convert_for_display(
            st.session_state.point_B["lat"], 
            st.session_state.point_B["lng"], 
            st.session_state.coord_system
        )
        ax.plot([a_lng, b_lng], [a_lat, b_lat], 'y-', linewidth=3, alpha=0.8, zorder=4, label='规划航线')
        
        # 添加方向箭头（中点）
        mid_lng = (a_lng + b_lng) / 2
        mid_lat = (a_lat + b_lat) / 2
        ax.annotate('→', (mid_lng, mid_lat), fontsize=20, color='orange',
                   ha='center', va='center', zorder=5)
    
    # 添加障碍物（红色圆圈）
    for i, obs in enumerate(st.session_state.obstacles):
        o_lng, o_lat = convert_for_display(obs["lat"], obs["lng"], "WGS-84")
        # 将半径（米）转换为度
        radius_deg = obs["radius"] / 111000
        circle = patches.Circle(
            (o_lng, o_lat), radius_deg,
            facecolor='red', alpha=0.3, edgecolor='darkred', linewidth=2
        )
        ax.add_patch(circle)
        ax.annotate(obs['name'], (o_lng, o_lat), xytext=(10, 10),
                   textcoords='offset points', fontsize=8, color='red',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.7))
    
    # 添加图例
    ax.legend(loc='upper right', fontsize=9, framealpha=0.9)
    
    # 显示距离信息
    if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
        distance = calculate_distance(
            st.session_state.point_A["lat"], st.session_state.point_A["lng"],
            st.session_state.point_B["lat"], st.session_state.point_B["lng"]
        )
        info_text = f'航线距离: {distance:.0f} 米 | 飞行高度: {st.session_state.flight_height} 米'
        ax.text(0.5, -0.08, info_text, transform=ax.transAxes, fontsize=10,
               ha='center', va='top', bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.7))
    
    # 添加坐标系信息
    ax.text(0.02, 0.98, f'坐标系: {st.session_state.coord_system}', transform=ax.transAxes,
           fontsize=8, verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.7))
    
    # 添加缩放级别信息
    ax.text(0.98, 0.98, f'缩放级别: {st.session_state.map_zoom}', transform=ax.transAxes,
           fontsize=8, ha='right', verticalalignment='top',
           bbox=dict(boxstyle='round', facecolor='white', alpha=0.7))
    
    plt.tight_layout()
    
    # 转换为图片
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    
    return buf

# ============================ 创建交互式地图（使用 folium 静态） ============================

def create_static_map_display():
    """创建静态地图显示"""
    
    try:
        img_buf = generate_static_map()
        st.image(img_buf, use_container_width=True)
    except Exception as e:
        st.error(f"地图生成失败: {str(e)}")
        
        # 降级方案：显示坐标表格
        st.info("📊 地图数据（坐标列表）")
        map_data = []
        if st.session_state.point_A["set"]:
            map_data.append({"类型": "起点A", "纬度": st.session_state.point_A["lat"], "经度": st.session_state.point_A["lng"]})
        if st.session_state.point_B["set"]:
            map_data.append({"类型": "终点B", "纬度": st.session_state.point_B["lat"], "经度": st.session_state.point_B["lng"]})
        for obs in st.session_state.obstacles:
            map_data.append({"类型": "障碍物", "名称": obs["name"], "纬度": obs["lat"], "经度": obs["lng"], "半径": f"{obs['radius']}m"})
        if map_data:
            st.dataframe(pd.DataFrame(map_data), use_container_width=True)

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
st.sidebar.markdown("# 🗺️ 地图控制")

st.session_state.map_zoom = st.sidebar.slider("缩放级别", 15, 19, st.session_state.map_zoom, 1)

st.sidebar.markdown("---")
st.sidebar.markdown("## 📖 操作说明")
st.sidebar.markdown("- 🟢 **绿色点**: 起点A")
st.sidebar.markdown("- 🔴 **红色点**: 终点B")
st.sidebar.markdown("- 🟡 **黄色线**: 规划航线")
st.sidebar.markdown("- 🔴 **红色圆圈**: 障碍物")
st.sidebar.markdown("- 💡 地图为示意图")
st.sidebar.markdown("- 📊 右侧表格查看详细坐标")

st.sidebar.markdown("---")
st.sidebar.markdown("### 📡 校园坐标参考")
st.sidebar.markdown("- 教学楼: 32.2328, 118.7485")
st.sidebar.markdown("- 图书馆: 32.2335, 118.7492")
st.sidebar.markdown("- 实验楼: 32.2330, 118.7500")
st.sidebar.markdown("- 食堂: 32.2325, 118.7495")
st.sidebar.markdown("- 体育馆: 32.2318, 118.7482")

# ============================ 航线规划页面 ============================

if page == "🗺️ 航线规划":
    st.title("🗺️ 航线规划")
    st.markdown("基于高德地图的无人机航线规划系统 | 支持 WGS-84 / GCJ-02 坐标系转换")
    
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
    
    # 地图显示
    st.markdown("### 🗺️ 高德地图（示意图）")
    st.markdown("💡 地图基于坐标数据生成 | 绿色为起点A | 红色为终点B/障碍物 | 黄色线为航线")
    
    # 显示静态地图
    create_static_map_display()
    
    # 坐标数据表格
    with st.expander("📊 坐标数据详情", expanded=False):
        coord_data = []
        if st.session_state.point_A["set"]:
            a_gcj_lng, a_gcj_lat = convert_for_display(
                st.session_state.point_A["lat"], 
                st.session_state.point_A["lng"], 
                st.session_state.coord_system
            )
            coord_data.append({
                "类型": "起点A",
                "原始坐标(输入)": f"{st.session_state.point_A['lat']:.6f}, {st.session_state.point_A['lng']:.6f}",
                "GCJ-02坐标(显示)": f"{a_gcj_lat:.6f}, {a_gcj_lng:.6f}"
            })
        if st.session_state.point_B["set"]:
            b_gcj_lng, b_gcj_lat = convert_for_display(
                st.session_state.point_B["lat"], 
                st.session_state.point_B["lng"], 
                st.session_state.coord_system
            )
            coord_data.append({
                "类型": "终点B",
                "原始坐标(输入)": f"{st.session_state.point_B['lat']:.6f}, {st.session_state.point_B['lng']:.6f}",
                "GCJ-02坐标(显示)": f"{b_gcj_lat:.6f}, {b_gcj_lng:.6f}"
            })
        for obs in st.session_state.obstacles:
            obs_gcj_lng, obs_gcj_lat = convert_for_display(obs["lat"], obs["lng"], "WGS-84")
            coord_data.append({
                "类型": f"障碍物-{obs['name']}",
                "原始坐标(输入)": f"{obs['lat']:.6f}, {obs['lng']:.6f}",
                "GCJ-02坐标(显示)": f"{obs_gcj_lat:.6f}, {obs_gcj_lng:.6f}"
            })
        if coord_data:
            st.dataframe(pd.DataFrame(coord_data), use_container_width=True)

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
    "© 2024 无人机地面站系统 | 地图: 高德地图示意图 | "
    "支持 WGS-84 / GCJ-02 坐标系转换 | 实时心跳监测"
)
