"""
无人机地面站系统 - 纯高德地图版本
使用高德地图 JavaScript API
需要高德地图 API Key
"""

import streamlit as st
import pandas as pd
import time
import math
from datetime import datetime

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
    """WGS-84 转 GCJ-02（GPS坐标转高德坐标）"""
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
    """GCJ-02 转 WGS-84（高德坐标转GPS坐标）"""
    if out_of_china(lng, lat):
        return lng, lat
    dlng, dlat = wgs84_to_gcj02(lng, lat)
    return lng * 2 - dlng, lat * 2 - dlat

def out_of_china(lng, lat):
    """判断坐标是否在中国境外"""
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)

def convert_to_gcj02(lat, lng, src_system):
    """转换为高德地图坐标（GCJ-02）"""
    if src_system == "WGS-84":
        return wgs84_to_gcj02(lng, lat)
    else:
        return lng, lat

# ============================ 距离计算 ============================

def calculate_distance(lat1, lng1, lat2, lng2):
    """使用 Haversine 公式计算两点间距离（米）"""
    R = 6371000  # 地球半径（米）
    
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
    
    # 高德地图 API Key（需要自己申请）
    if "amap_key" not in st.session_state:
        st.session_state.amap_key = "YOUR_AMAP_KEY"  # 替换为你的 Key
    
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

# ============================ 生成高德地图 HTML ============================

def generate_map_html():
    """生成包含高德地图的 HTML 代码"""
    
    # 获取显示坐标（GCJ-02）
    if st.session_state.point_A["set"]:
        a_lng, a_lat = convert_to_gcj02(
            st.session_state.point_A["lat"], 
            st.session_state.point_A["lng"], 
            st.session_state.coord_system
        )
    else:
        a_lng, a_lat = None, None
    
    if st.session_state.point_B["set"]:
        b_lng, b_lat = convert_to_gcj02(
            st.session_state.point_B["lat"], 
            st.session_state.point_B["lng"], 
            st.session_state.coord_system
        )
    else:
        b_lng, b_lat = None, None
    
    # 障碍物坐标转换
    obstacles_data = []
    for obs in st.session_state.obstacles:
        o_lng, o_lat = convert_to_gcj02(obs["lat"], obs["lng"], "WGS-84")
        obstacles_data.append({
            "lng": o_lng,
            "lat": o_lat,
            "radius": obs["radius"],
            "name": obs["name"]
        })
    
    # 计算航线距离
    distance = 0
    if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
        distance = calculate_distance(
            st.session_state.point_A["lat"], st.session_state.point_A["lng"],
            st.session_state.point_B["lat"], st.session_state.point_B["lng"]
        )
    
    # 确定地图中心点
    if a_lat:
        center_lat, center_lng = a_lat, a_lng
    elif b_lat:
        center_lat, center_lng = b_lat, b_lng
    else:
        center_lat, center_lng = 32.2332, 118.7492
    
    # 生成 HTML
    html_code = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>高德地图 - 无人机航线规划</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: "Microsoft YaHei", sans-serif; }}
            #container {{ width: 100%; height: 100%; position: relative; }}
            .legend {{
                position: absolute;
                bottom: 20px;
                right: 20px;
                background: rgba(0,0,0,0.75);
                color: white;
                padding: 10px 15px;
                border-radius: 8px;
                z-index: 1000;
                font-size: 12px;
                pointer-events: none;
                backdrop-filter: blur(5px);
                font-family: monospace;
            }}
            .legend p {{ margin: 5px 0; }}
            .legend .green {{ color: #00ff00; font-weight: bold; }}
            .legend .red {{ color: #ff0000; font-weight: bold; }}
            .legend .yellow {{ color: #ffff00; font-weight: bold; }}
            .distance-label {{
                position: absolute;
                top: 20px;
                left: 50%;
                transform: translateX(-50%);
                background: rgba(0,0,0,0.7);
                color: #ffff00;
                padding: 8px 16px;
                border-radius: 25px;
                z-index: 1000;
                font-size: 14px;
                font-weight: bold;
                pointer-events: none;
                font-family: monospace;
                white-space: nowrap;
            }}
            .info-panel {{
                position: absolute;
                bottom: 20px;
                left: 20px;
                background: rgba(0,0,0,0.6);
                color: white;
                padding: 8px 12px;
                border-radius: 8px;
                z-index: 1000;
                font-size: 11px;
                pointer-events: none;
                font-family: monospace;
            }}
        </style>
    </head>
    <body>
        <div id="container"></div>
        <div class="distance-label">
            ✈️ 航线距离: {distance:.0f} 米 | 飞行高度: {st.session_state.flight_height} 米
        </div>
        <div class="legend">
            <p><strong>📖 图例</strong></p>
            <p><span class="green">●</span> 起点A</p>
            <p><span class="red">●</span> 终点B</p>
            <p><span class="yellow">━</span> 规划航线</p>
            <p><span class="red">●</span> 障碍物</p>
        </div>
        <div class="info-panel">
            🖱️ 鼠标拖拽平移 | 🔍 滚轮缩放 | 🖱️ 右键拖拽旋转
        </div>
        
        <script src="https://webapi.amap.com/maps?v=2.0&key={st.session_state.amap_key}"></script>
        <script>
        var map;
        
        // 初始化地图
        function initMap() {{
            // 创建地图
            map = new AMap.Map('container', {{
                center: [{center_lng}, {center_lat}],
                zoom: {st.session_state.map_zoom},
                viewMode: '3D',
                pitch: 50,
                rotation: 0
            }});
            
            // 添加控件
            map.addControl(new AMap.Scale());
            map.addControl(new AMap.ToolBar({{
                position: 'RT'
            }}));
            map.addControl(new AMap.ControlBar({{
                position: 'RB'
            }}));
            
            // 添加鹰眼图
            map.addControl(new AMap.HawkEye({{
                opened: false
            }}));
            
            '''
    
    # 添加起点A
    if a_lat:
        html_code += f'''
            // 起点A 标记
            var aMarker = new AMap.Marker({{
                position: [{a_lng}, {a_lat}],
                title: '起点A',
                icon: new AMap.Icon({{
                    size: new AMap.Size(36, 36),
                    image: 'https://webapi.amap.com/theme/v1.3/markers/n/mark_b.png',
                    imageSize: new AMap.Size(36, 36)
                }}),
                label: {{
                    content: '<div style="background:#00aa00;color:white;padding:2px 8px;border-radius:4px;font-size:12px;">🚁 起点A</div>',
                    offset: new AMap.Pixel(0, -35)
                }}
            }});
            aMarker.setMap(map);
            
            // 起点A 圆形区域
            var aCircle = new AMap.Circle({{
                center: [{a_lng}, {a_lat}],
                radius: 25,
                strokeColor: '#00ff00',
                strokeOpacity: 0.8,
                strokeWeight: 2,
                fillColor: '#00ff00',
                fillOpacity: 0.15
            }});
            aCircle.setMap(map);
        '''
    
    # 添加终点B
    if b_lat:
        html_code += f'''
            // 终点B 标记
            var bMarker = new AMap.Marker({{
                position: [{b_lng}, {b_lat}],
                title: '终点B',
                icon: new AMap.Icon({{
                    size: new AMap.Size(36, 36),
                    image: 'https://webapi.amap.com/theme/v1.3/markers/n/mark_r.png',
                    imageSize: new AMap.Size(36, 36)
                }}),
                label: {{
                    content: '<div style="background:#cc0000;color:white;padding:2px 8px;border-radius:4px;font-size:12px;">🎯 终点B</div>',
                    offset: new AMap.Pixel(0, -35)
                }}
            }});
            bMarker.setMap(map);
            
            // 终点B 圆形区域
            var bCircle = new AMap.Circle({{
                center: [{b_lng}, {b_lat}],
                radius: 25,
                strokeColor: '#ff0000',
                strokeOpacity: 0.8,
                strokeWeight: 2,
                fillColor: '#ff0000',
                fillOpacity: 0.15
            }});
            bCircle.setMap(map);
        '''
    
    # 添加航线
    if a_lat and b_lat:
        html_code += f'''
            // 规划航线
            var linePath = [
                [{a_lng}, {a_lat}],
                [{b_lng}, {b_lat}]
            ];
            var polyline = new AMap.Polyline({{
                path: linePath,
                strokeColor: '#ffff00',
                strokeOpacity: 0.9,
                strokeWeight: 5,
                lineCap: 'round',
                lineJoin: 'round',
                showDir: true
            }});
            polyline.setMap(map);
        '''
    
    # 添加障碍物
    for i, obs in enumerate(obstacles_data):
        html_code += f'''
            // 障碍物: {obs["name"]}
            var obstacleCircle_{i} = new AMap.Circle({{
                center: [{obs["lng"]}, {obs["lat"]}],
                radius: {obs["radius"]},
                strokeColor: '#ff4444',
                strokeOpacity: 0.8,
                strokeWeight: 2,
                fillColor: '#ff0000',
                fillOpacity: 0.35
            }});
            obstacleCircle_{i}.setMap(map);
            
            // 障碍物标签
            var obstacleLabel_{i} = new AMap.Marker({{
                position: [{obs["lng"]}, {obs["lat"]}],
                content: '<div style="background:#ff0000;color:white;padding:2px 6px;border-radius:12px;font-size:11px;font-weight:bold;">⚠️ {obs["name"]}</div>',
                offset: new AMap.Pixel(0, -20)
            }});
            obstacleLabel_{i}.setMap(map);
        '''
    
    html_code += '''
        }
        
        // 地图加载完成
        window.onload = initMap;
        </script>
    </body>
    </html>
    '''
    
    return html_code

# ============================ 页面配置 ============================

st.set_page_config(
    page_title="无人机地面站系统",
    page_icon="🛸",
    layout="wide"
)

# ============================ 侧边栏 ============================

st.sidebar.markdown("# 🚁 无人机地面站系统")
st.sidebar.markdown("---")

st.sidebar.markdown("# 🔑 地图配置")
st.sidebar.markdown("### 高德地图 API Key")

# API Key 输入
amap_key_input = st.sidebar.text_input(
    "API Key",
    value=st.session_state.amap_key,
    type="password",
    help="申请地址: https://lbs.amap.com/"
)
if amap_key_input:
    st.session_state.amap_key = amap_key_input

# API Key 提示
if st.session_state.amap_key == "YOUR_AMAP_KEY" or not st.session_state.amap_key:
    st.sidebar.warning("⚠️ 请输入高德地图 API Key")
    st.sidebar.info("📌 如何获取？\n1. 访问 lbs.amap.com\n2. 注册/登录\n3. 控制台 → 应用管理 → 创建应用\n4. 选择 Web端(JS API) 服务")

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
st.sidebar.markdown("- 🖱️ 鼠标拖拽: 平移地图")
st.sidebar.markdown("- 🔍 鼠标滚轮: 缩放地图")
st.sidebar.markdown("- 🖱️ 右键拖拽: 旋转3D视角")
st.sidebar.markdown("- 🟢 绿色: 起点A")
st.sidebar.markdown("- 🔴 红色: 终点B/障碍物")
st.sidebar.markdown("- 🟡 黄色: 规划航线")

# 导航
st.sidebar.markdown("---")
st.sidebar.markdown("# 🧭 导航")
page = st.sidebar.radio("功能页面", ["🗺️ 航线规划", "💓 飞行监控"])

# ============================ 航线规划页面 ============================

if page == "🗺️ 航线规划":
    st.title("🗺️ 无人机航线规划系统")
    st.markdown("基于高德地图的3D无人机航线规划 | 支持 WGS-84 / GCJ-02 坐标系转换")
    
    # 检查 API Key
    if not st.session_state.amap_key or st.session_state.amap_key == "YOUR_AMAP_KEY":
        st.error("⚠️ 请先在左侧边栏输入高德地图 API Key！")
        with st.expander("📖 如何获取高德地图 API Key？"):
            st.markdown("""
            ### 获取步骤：
            
            1. 访问 **https://lbs.amap.com/**
            2. 点击右上角「注册」或「登录」
            3. 进入「控制台」→「应用管理」→「我的应用」
            4. 点击「创建新应用」
            5. 填写应用名称（如：无人机地面站）
            6. 选择「Web端(JS API)」服务
            7. 点击「创建」，复制生成的 Key
            8. 将 Key 粘贴到左侧边栏输入框
            """)
        st.stop()
    
    col1, col2 = st.columns([1, 1.2])
    
    with col1:
        st.markdown("### 🎮 控制面板")
        
        # 起点A
        st.markdown("#### 📍 起点A")
        col_a1, col_a2 = st.columns(2)
        with col_a1:
            a_lat = st.number_input(
                "纬度", 
                value=st.session_state.point_A["lat"], 
                format="%.6f", 
                key="a_lat"
            )
        with col_a2:
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
        
        st.markdown("---")
        
        # 终点B
        st.markdown("#### 🎯 终点B")
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            b_lat = st.number_input(
                "纬度", 
                value=st.session_state.point_B["lat"], 
                format="%.6f", 
                key="b_lat"
            )
        with col_b2:
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
        
        st.markdown("---")
        
        # 飞行参数
        st.markdown("#### ✈️ 飞行参数")
        st.session_state.flight_height = st.number_input(
            "飞行高度 (m)", 
            value=st.session_state.flight_height, 
            step=5.0,
            help="无人机飞行的高度"
        )
        
        st.markdown("---")
        
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
        
        # 状态显示卡片
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
    st.markdown("### 🛰️ 高德3D地图")
    st.markdown("💡 **操作提示**：鼠标拖拽平移 | 滚轮缩放 | 右键拖拽旋转3D视角")
    
    # 生成并显示地图
    try:
        map_html = generate_map_html()
        st.components.v1.html(map_html, height=550, width=1200, scrolling=False)
    except Exception as e:
        st.error(f"地图加载失败: {str(e)}")
        st.info("请检查 API Key 是否正确，或者刷新页面重试")

# ============================ 飞行监控页面 ============================

else:
    st.title("🛸 无人机心跳监测系统")
    st.markdown("模拟无人机每秒发送心跳包，地面站实时监测，3秒未收到自动报警")
    
    # 自动刷新（每秒刷新一次）
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
    "© 2024 无人机地面站系统 | 底图: 高德地图 | "
    "支持 WGS-84 / GCJ-02 坐标系转换 | 实时心跳监测"
)
