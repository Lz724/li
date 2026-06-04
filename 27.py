"""
无人机地面站系统 - 纯高德地图版本
包含调试功能，帮助排查 Key 问题
"""

import streamlit as st
import pandas as pd
import time
import math
from datetime import datetime

# ============================ 坐标系转换算法 ============================

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

# ============================ 心跳函数 ============================

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

# ============================ 生成高德地图 HTML ============================

def generate_map_html():
    """生成高德地图 HTML（带错误检测）"""
    
    # 获取显示坐标
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
    
    # 地图中心
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
        <title>高德地图</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body, html {{ width: 100%; height: 100%; }}
            #container {{ width: 100%; height: 100%; }}
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
            }}
            .distance-label {{
                position: absolute;
                top: 20px;
                left: 50%;
                transform: translateX(-50%);
                background: rgba(0,0,0,0.7);
                color: #ffff00;
                padding: 6px 12px;
                border-radius: 20px;
                z-index: 1000;
                font-size: 12px;
                font-weight: bold;
                pointer-events: none;
                white-space: nowrap;
            }}
            .error-msg {{
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: rgba(255,0,0,0.8);
                color: white;
                padding: 15px 25px;
                border-radius: 8px;
                z-index: 2000;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        <div id="container"></div>
        <div class="distance-label">
            ✈️ 航线距离: {distance:.0f}米 | 高度: {st.session_state.flight_height}m
        </div>
        <div class="legend">
            <p><strong>图例</strong></p>
            <p><span style="color:#00ff00;">●</span> 起点A</p>
            <p><span style="color:#ff0000;">●</span> 终点B</p>
            <p><span style="color:#ffff00;">━</span> 航线</p>
            <p><span style="color:#ff0000;">●</span> 障碍物</p>
        </div>
        
        <script src="https://webapi.amap.com/maps?v=2.0&key={st.session_state.amap_key}"></script>
        <script>
        var map;
        
        function initMap() {{
            try {{
                map = new AMap.Map('container', {{
                    center: [{center_lng}, {center_lat}],
                    zoom: {st.session_state.map_zoom},
                    viewMode: '3D',
                    pitch: 45
                }});
                
                map.addControl(new AMap.Scale());
                map.addControl(new AMap.ToolBar());
                map.addControl(new AMap.ControlBar());
                
                '''
    
    if a_lat:
        html_code += f'''
                var aMarker = new AMap.Marker({{
                    position: [{a_lng}, {a_lat}],
                    title: '起点A',
                    label: {{
                        content: '<div style="background:#00aa00;color:white;padding:2px 6px;border-radius:4px;">🚁 A点</div>',
                        offset: new AMap.Pixel(0, -30)
                    }}
                }});
                aMarker.setMap(map);
                
                new AMap.Circle({{
                    center: [{a_lng}, {a_lat}],
                    radius: 25,
                    strokeColor: '#00ff00',
                    fillColor: '#00ff00',
                    fillOpacity: 0.15
                }}).setMap(map);
        '''
    
    if b_lat:
        html_code += f'''
                var bMarker = new AMap.Marker({{
                    position: [{b_lng}, {b_lat}],
                    title: '终点B',
                    label: {{
                        content: '<div style="background:#cc0000;color:white;padding:2px 6px;border-radius:4px;">🎯 B点</div>',
                        offset: new AMap.Pixel(0, -30)
                    }}
                }});
                bMarker.setMap(map);
                
                new AMap.Circle({{
                    center: [{b_lng}, {b_lat}],
                    radius: 25,
                    strokeColor: '#ff0000',
                    fillColor: '#ff0000',
                    fillOpacity: 0.15
                }}).setMap(map);
        '''
    
    if a_lat and b_lat:
        html_code += f'''
                var line = new AMap.Polyline({{
                    path: [[{a_lng}, {a_lat}], [{b_lng}, {b_lat}]],
                    strokeColor: '#ffff00',
                    strokeWeight: 5
                }});
                line.setMap(map);
        '''
    
    for i, obs in enumerate(obstacles_data):
        html_code += f'''
                new AMap.Circle({{
                    center: [{obs["lng"]}, {obs["lat"]}],
                    radius: {obs["radius"]},
                    strokeColor: '#ff4444',
                    fillColor: '#ff0000',
                    fillOpacity: 0.35
                }}).setMap(map);
                
                new AMap.Marker({{
                    position: [{obs["lng"]}, {obs["lat"]}],
                    content: '<div style="background:#ff0000;color:white;padding:2px 5px;border-radius:10px;font-size:10px;">⚠️ {obs["name"]}</div>',
                    offset: new AMap.Pixel(0, -15)
                }}).setMap(map);
        '''
    
    html_code += '''
            } catch(e) {
                document.getElementById('container').innerHTML = '<div class="error-msg">地图加载失败<br>请检查 API Key 是否正确</div>';
                console.error(e);
            }
        }
        
        window.onload = initMap;
        </script>
    </body>
    </html>
    '''
    
    return html_code

# ============================ 页面配置 ============================

st.set_page_config(page_title="无人机地面站系统", layout="wide")

# 侧边栏
st.sidebar.title("🚁 无人机地面站")
st.sidebar.markdown("---")

st.sidebar.subheader("🔑 高德地图 API Key")
amap_key_input = st.sidebar.text_input(
    "API Key",
    value=st.session_state.amap_key,
    type="password",
    help="获取地址: https://lbs.amap.com/"
)
if amap_key_input:
    st.session_state.amap_key = amap_key_input

# API Key 验证提示
if not st.session_state.amap_key:
    st.sidebar.error("❌ 请输入高德地图 API Key")
elif len(st.session_state.amap_key) < 20:
    st.sidebar.warning("⚠️ API Key 长度异常，请检查是否正确")
else:
    st.sidebar.success("✅ API Key 已设置")

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

# ============================ 航线规划页面 ============================

if page == "🗺️ 航线规划":
    st.title("🗺️ 无人机航线规划系统")
    
    if not st.session_state.amap_key:
        st.error("⚠️ 请先在左侧边栏输入高德地图 API Key！")
        with st.expander("📖 如何获取高德地图 API Key？"):
            st.markdown("""
            ### 步骤：
            1. 访问 **https://lbs.amap.com/**
            2. 注册/登录账号
            3. 进入「控制台」→「应用管理」→「我的应用」
            4. 点击「创建新应用」
            5. 应用名称填写「无人机地面站」
            6. 选择服务类型：「Web端(JS API)」
            7. 创建成功后复制 Key
            """)
        st.stop()
    
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
    st.info("💡 鼠标拖拽平移 | 滚轮缩放 | 右键拖拽旋转")
    
    try:
        map_html = generate_map_html()
        st.components.v1.html(map_html, height=550, width=1200)
    except Exception as e:
        st.error(f"地图加载失败: {str(e)}")

# ============================ 飞行监控页面 ============================

else:
    st.title("🛸 无人机心跳监测系统")
    st.markdown("每秒发送心跳包，3秒未收到自动报警")
    
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
    with col2:
        if st.session_state.running and st.session_state.last_ts:
            since = time.time() - st.session_state.last_ts
            if since < 1:
                st.success(f"💓 最后心跳: {since:.1f}秒前")
            elif since < 3:
                st.warning(f"💓 最后心跳: {since:.1f}秒前")
            else:
                st.error(f"💔 最后心跳: {since:.1f}秒前")
    
    if st.session_state.records:
        df = pd.DataFrame(st.session_state.records, columns=["序号", "时间戳"])
        df["时间"] = pd.to_datetime(df["时间戳"], unit="s")
        st.line_chart(df.set_index("时间")["序号"])
        
        df["接收时间"] = df["时间戳"].apply(lambda x: datetime.fromtimestamp(x).strftime("%H:%M:%S"))
        st.dataframe(df[["序号", "接收时间"]])

st.markdown("---")
st.markdown("© 无人机地面站 | 高德地图 | WGS-84/GCJ-02 坐标转换")
