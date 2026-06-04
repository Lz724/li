"""
无人机地面站系统 - 高德地图版本
"""

import streamlit as st
import pandas as pd
import time
import math
from datetime import datetime

# ============================ 坐标系转换 ============================

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

def convert_to_gcj02(lat, lng, src_system):
    if src_system == "WGS-84":
        return wgs84_to_gcj02(lng, lat)
    else:
        return lng, lat

def calculate_distance(lat1, lng1, lat2, lng2):
    R = 6371000
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# ============================ 初始化 ============================

def init_state():
    if "amap_key" not in st.session_state:
        st.session_state.amap_key = ""
    
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

# ============================ 生成地图 HTML ============================

def generate_map_html():
    """生成高德地图 HTML"""
    
    # 获取坐标
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
    
    # 障碍物
    obstacles_data = []
    for obs in st.session_state.obstacles:
        o_lng, o_lat = convert_to_gcj02(obs["lat"], obs["lng"], "WGS-84")
        obstacles_data.append({
            "lng": o_lng,
            "lat": o_lat,
            "radius": obs["radius"],
            "name": obs["name"]
        })
    
    # 距离
    distance = 0
    if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
        distance = calculate_distance(
            st.session_state.point_A["lat"], st.session_state.point_A["lng"],
            st.session_state.point_B["lat"], st.session_state.point_B["lng"]
        )
    
    # 中心点
    if a_lat:
        center_lat, center_lng = a_lat, a_lng
    elif b_lat:
        center_lat, center_lng = b_lat, b_lng
    else:
        center_lat, center_lng = 32.2332, 118.7492
    
    # 安全处理 Key
    api_key = st.session_state.amap_key.strip()
    
    html_code = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>高德地图</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body, html {{ width: 100%; height: 100%; }}
            #container {{ width: 100%; height: 100%; }}
            .legend {{
                position: absolute;
                bottom: 20px;
                right: 20px;
                background: rgba(0,0,0,0.7);
                color: white;
                padding: 8px 12px;
                border-radius: 8px;
                z-index: 1000;
                font-size: 11px;
                pointer-events: none;
            }}
            .distance-label {{
                position: absolute;
                top: 20px;
                left: 50%;
                transform: translateX(-50%);
                background: rgba(0,0,0,0.7);
                color: #ffff00;
                padding: 5px 10px;
                border-radius: 20px;
                z-index: 1000;
                font-size: 11px;
                font-weight: bold;
                pointer-events: none;
                white-space: nowrap;
            }}
        </style>
    </head>
    <body>
        <div id="container"></div>
        <div class="distance-label">✈️ 航线距离: {distance:.0f}m | 高度: {st.session_state.flight_height}m</div>
        <div class="legend">
            <p><span style="color:#0f0;">●</span> A点 <span style="color:#f00;">●</span> B点 <span style="color:#ff0;">━</span> 航线 <span style="color:#f00;">●</span> 障碍物</p>
        </div>
        
        <script>
        window._AMapSecurityConfig = {{
            securityJsCode: ''
        }};
        </script>
        <script src="https://webapi.amap.com/maps?v=2.0&key={api_key}"></script>
        <script>
        var map;
        
        function loadMap() {{
            try {{
                map = new AMap.Map('container', {{
                    center: [{center_lng}, {center_lat}],
                    zoom: {st.session_state.map_zoom},
                    viewMode: '3D',
                    pitch: 50
                }});
                
                map.addControl(new AMap.Scale());
                map.addControl(new AMap.ToolBar());
        '''
    
    if a_lat:
        html_code += f'''
                new AMap.Marker({{
                    position: [{a_lng}, {a_lat}],
                    label: {{ content: '🚁 A', offset: new AMap.Pixel(0, -20) }}
                }}).setMap(map);
                new AMap.Circle({{
                    center: [{a_lng}, {a_lat}],
                    radius: 20,
                    strokeColor: '#0f0',
                    fillColor: '#0f0',
                    fillOpacity: 0.2
                }}).setMap(map);
        '''
    
    if b_lat:
        html_code += f'''
                new AMap.Marker({{
                    position: [{b_lng}, {b_lat}],
                    label: {{ content: '🎯 B', offset: new AMap.Pixel(0, -20) }}
                }}).setMap(map);
                new AMap.Circle({{
                    center: [{b_lng}, {b_lat}],
                    radius: 20,
                    strokeColor: '#f00',
                    fillColor: '#f00',
                    fillOpacity: 0.2
                }}).setMap(map);
        '''
    
    if a_lat and b_lat:
        html_code += f'''
                new AMap.Polyline({{
                    path: [[{a_lng}, {a_lat}], [{b_lng}, {b_lat}]],
                    strokeColor: '#ff0',
                    strokeWeight: 4
                }}).setMap(map);
        '''
    
    for obs in obstacles_data:
        html_code += f'''
                new AMap.Circle({{
                    center: [{obs["lng"]}, {obs["lat"]}],
                    radius: {obs["radius"]},
                    strokeColor: '#f44',
                    fillColor: '#f00',
                    fillOpacity: 0.3
                }}).setMap(map);
                new AMap.Marker({{
                    position: [{obs["lng"]}, {obs["lat"]}],
                    content: '<div style="background:#f00;color:white;padding:0 4px;border-radius:10px;font-size:10px;">{obs["name"]}</div>',
                    offset: new AMap.Pixel(0, -15)
                }}).setMap(map);
        '''
    
    html_code += '''
            } catch(e) {
                document.getElementById('container').innerHTML = '<div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);background:#f00;color:white;padding:20px;border-radius:8px;">地图加载失败<br>请检查API Key</div>';
            }
        }
        
        window.onload = loadMap;
        </script>
    </body>
    </html>
    '''
    
    return html_code

# ============================ 页面 ============================

st.set_page_config(page_title="无人机地面站系统", layout="wide")

# 侧边栏
st.sidebar.title("🚁 无人机地面站")
st.sidebar.markdown("---")

st.sidebar.subheader("🔑 高德地图 API Key")
amap_key_input = st.sidebar.text_input(
    "API Key",
    value=st.session_state.amap_key,
    type="password",
    help="获取: https://lbs.amap.com/"
)
if amap_key_input:
    st.session_state.amap_key = amap_key_input

# 验证 Key
if not st.session_state.amap_key:
    st.sidebar.error("❌ 请输入 API Key")
elif len(st.session_state.amap_key) < 30:
    st.sidebar.warning(f"⚠️ Key 长度 {len(st.session_state.amap_key)}，可能不完整")
else:
    st.sidebar.success(f"✅ Key 已设置 ({len(st.session_state.amap_key)}位)")

st.sidebar.markdown("---")

st.sidebar.subheader("📐 坐标系")
coord_sys = st.sidebar.selectbox(
    "输入坐标系",
    ["WGS-84", "GCJ-02(高德)"],
    index=0 if st.session_state.coord_system == "WGS-84" else 1
)
st.session_state.coord_system = coord_sys.split("(")[0]

st.sidebar.subheader("🗺️ 地图控制")
st.session_state.map_zoom = st.sidebar.slider("缩放级别", 15, 18, st.session_state.map_zoom, 1)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📖 操作说明")
st.sidebar.markdown("- 🖱️ 拖拽: 平移")
st.sidebar.markdown("- 🔍 滚轮: 缩放")
st.sidebar.markdown("- 🖱️ 右键拖拽: 旋转")

st.sidebar.markdown("---")
page = st.sidebar.radio("📋 功能页面", ["🗺️ 航线规划", "💓 飞行监控"])

# ============================ 航线规划 ============================

if page == "🗺️ 航线规划":
    st.title("🗺️ 无人机航线规划系统")
    
    if not st.session_state.amap_key:
        st.error("⚠️ 请先在左侧边栏输入高德地图 API Key")
        st.stop()
    
    if len(st.session_state.amap_key) < 30:
        st.warning("⚠️ API Key 长度异常，请确认是否正确复制了完整的 Key")
        st.info("正确的 Key 应该是一串约 32 位的字符")
    
    col1, col2 = st.columns([1, 1.2])
    
    with col1:
        st.subheader("🎮 控制面板")
        
        st.markdown("#### 📍 起点A")
        a_lat = st.number_input("纬度", value=st.session_state.point_A["lat"], format="%.6f", key="a_lat")
        a_lng = st.number_input("经度", value=st.session_state.point_A["lng"], format="%.6f", key="a_lng")
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("📍 设置A点", use_container_width=True):
                st.session_state.point_A = {"lat": a_lat, "lng": a_lng, "set": True}
                st.rerun()
        with col_btn2:
            if st.button("🗑️ 清除A点", use_container_width=True):
                st.session_state.point_A["set"] = False
                st.rerun()
        
        st.markdown("#### 🎯 终点B")
        b_lat = st.number_input("纬度", value=st.session_state.point_B["lat"], format="%.6f", key="b_lat")
        b_lng = st.number_input("经度", value=st.session_state.point_B["lng"], format="%.6f", key="b_lng")
        col_btn3, col_btn4 = st.columns(2)
        with col_btn3:
            if st.button("🎯 设置B点", use_container_width=True):
                st.session_state.point_B = {"lat": b_lat, "lng": b_lng, "set": True}
                st.rerun()
        with col_btn4:
            if st.button("🗑️ 清除B点", use_container_width=True):
                st.session_state.point_B["set"] = False
                st.rerun()
        
        st.markdown("#### ✈️ 飞行参数")
        st.session_state.flight_height = st.number_input("飞行高度 (m)", value=st.session_state.flight_height, step=5.0)
        
        st.markdown("#### 🚧 障碍物")
        with st.expander("➕ 添加障碍物"):
            obs_name = st.text_input("名称", "新障碍物")
            col_o1, col_o2 = st.columns(2)
            with col_o1:
                obs_lat = st.number_input("纬度", value=32.2330, format="%.6f")
            with col_o2:
                obs_lng = st.number_input("经度", value=118.7495, format="%.6f")
            obs_radius = st.number_input("半径(m)", value=25, step=5)
            if st.button("✅ 添加"):
                st.session_state.obstacles.append({"lat": obs_lat, "lng": obs_lng, "radius": obs_radius, "name": obs_name})
                st.rerun()
    
    with col2:
        st.subheader("📊 系统状态")
        
        if st.session_state.point_A["set"]:
            st.success(f"✅ A点: {st.session_state.point_A['lat']:.6f}, {st.session_state.point_A['lng']:.6f}")
        else:
            st.warning("❌ A点未设")
        
        if st.session_state.point_B["set"]:
            st.success(f"✅ B点: {st.session_state.point_B['lat']:.6f}, {st.session_state.point_B['lng']:.6f}")
        else:
            st.warning("❌ B点未设")
        
        if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
            dist = calculate_distance(a_lat, a_lng, b_lat, b_lng)
            st.info(f"📏 距离: {dist:.1f} 米")
        
        st.info(f"✈️ 高度: {st.session_state.flight_height} m")
        st.info(f"🗺️ 坐标系: {st.session_state.coord_system}")
        
        if st.session_state.obstacles:
            st.write("**障碍物列表**")
            for i, obs in enumerate(st.session_state.obstacles):
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.write(f"{i+1}. {obs['name']} ({obs['radius']}m)")
                with col_b:
                    if st.button("🗑️", key=f"del_{i}"):
                        st.session_state.obstacles.pop(i)
                        st.rerun()
    
    st.markdown("### 🗺️ 高德3D地图")
    
    try:
        map_html = generate_map_html()
        st.components.v1.html(map_html, height=550, width=1200)
    except Exception as e:
        st.error(f"地图加载失败: {str(e)}")

# ============================ 飞行监控 ============================

else:
    st.title("🛸 无人机心跳监测系统")
    
    if st.session_state.running:
        st.markdown('<meta http-equiv="refresh" content="1">', unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🚀 启动", use_container_width=True):
            reset_monitor()
            st.session_state.running = True
            add_heartbeat(1, time.time())
    with c2:
        if st.button("⏸️ 暂停/恢复", use_container_width=True):
            st.session_state.running = not st.session_state.running
    with c3:
        if st.button("🛑 停止", use_container_width=True):
            reset_monitor()
    
    if st.session_state.running:
        now = time.time()
        last = st.session_state.last_ts
        if last is None:
            add_heartbeat(1, now)
        else:
            diff = now - last
            if diff >= 1.0:
                for i in range(min(int(diff), 5)):
                    add_heartbeat(st.session_state.seq + 1, last + i + 1)
        
        if st.session_state.last_ts and (time.time() - st.session_state.last_ts) > 3.0:
            st.error(f"⚠️ 超时！已 {time.time() - st.session_state.last_ts:.1f} 秒无心跳")
        else:
            st.success("✅ 连接正常")
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("最新心跳序号", st.session_state.seq or "—")
        status = "✈️ 飞行中" if st.session_state.running else "🛬 已停止"
        st.write(f"状态: {status}")
    
    if st.session_state.records:
        df = pd.DataFrame(st.session_state.records, columns=["序号", "时间戳"])
        df["时间"] = pd.to_datetime(df["时间戳"], unit="s")
        st.line_chart(df.set_index("时间")["序号"])
        df["接收时间"] = df["时间戳"].apply(lambda x: datetime.fromtimestamp(x).strftime("%H:%M:%S"))
        st.dataframe(df[["序号", "接收时间"]])

st.markdown("---")
st.markdown("© 无人机地面站 | 高德地图")
