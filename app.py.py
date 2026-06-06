"""
无人机地面站系统 - 高德静态卫星图版本
使用高德静态图 API，无需 API Key，直接显示卫星影像
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

def convert_for_display(lat, lng, src_system):
    if src_system == "WGS-84":
        return wgs84_to_gcj02(lng, lat)
    else:
        return lng, lat

# ============================ 距离计算 ============================

def calculate_distance(lat1, lng1, lat2, lng2):
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

# ============================ 心跳监控函数 ============================

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

# ============================ 生成高德静态卫星图 ============================

def get_static_satellite_map():
    """获取高德静态卫星图"""
    
    # 确定地图中心（使用 GCJ-02 坐标）
    if st.session_state.point_A["set"]:
        lng, lat = convert_for_display(
            st.session_state.point_A["lat"], 
            st.session_state.point_A["lng"], 
            st.session_state.coord_system
        )
    elif st.session_state.point_B["set"]:
        lng, lat = convert_for_display(
            st.session_state.point_B["lat"], 
            st.session_state.point_B["lng"], 
            st.session_state.coord_system
        )
    else:
        lng, lat = 118.7492, 32.2332
    
    # 缩放级别
    zoom = min(18, max(3, st.session_state.map_zoom))
    
    # 构建 HTML 地图（使用高德卫星瓦片）
    map_html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: "Microsoft YaHei", sans-serif; }}
            #map {{
                width: 100%;
                height: 100%;
                position: relative;
                background: #1a1a2e;
            }}
            .marker {{
                position: absolute;
                width: 30px;
                height: 30px;
                transform: translate(-50%, -50%);
                cursor: pointer;
                z-index: 1000;
            }}
            .marker-a {{
                background: radial-gradient(circle, #00ff00, #008800);
                border-radius: 50%;
                border: 2px solid white;
                box-shadow: 0 0 10px rgba(0,255,0,0.5);
            }}
            .marker-b {{
                background: radial-gradient(circle, #ff0000, #880000);
                border-radius: 50%;
                border: 2px solid white;
                box-shadow: 0 0 10px rgba(255,0,0,0.5);
            }}
            .marker-obstacle {{
                background: radial-gradient(circle, #ff6600, #cc3300);
                border-radius: 50%;
                border: 2px solid white;
                box-shadow: 0 0 10px rgba(255,102,0,0.5);
            }}
            .marker-label {{
                position: absolute;
                top: -25px;
                left: 15px;
                background: rgba(0,0,0,0.7);
                color: white;
                padding: 2px 6px;
                border-radius: 4px;
                font-size: 10px;
                white-space: nowrap;
                pointer-events: none;
            }}
            .info-panel {{
                position: absolute;
                bottom: 20px;
                left: 20px;
                background: rgba(0,0,0,0.75);
                color: white;
                padding: 10px 15px;
                border-radius: 8px;
                z-index: 1001;
                font-size: 12px;
                backdrop-filter: blur(5px);
                pointer-events: none;
            }}
            .legend {{
                position: absolute;
                bottom: 20px;
                right: 20px;
                background: rgba(0,0,0,0.75);
                color: white;
                padding: 10px 15px;
                border-radius: 8px;
                z-index: 1001;
                font-size: 11px;
                backdrop-filter: blur(5px);
                pointer-events: none;
            }}
            .legend-item {{
                margin: 3px 0;
                display: flex;
                align-items: center;
            }}
            .legend-color {{
                width: 16px;
                height: 16px;
                border-radius: 50%;
                margin-right: 8px;
            }}
            .legend-line {{
                width: 30px;
                height: 3px;
                margin-right: 8px;
            }}
        </style>
    </head>
    <body>
        <div id="map"></div>
        <div class="info-panel">
            <strong>🗺️ 高德卫星图</strong><br>
            缩放级别: {zoom} | 中心点: {lat:.6f}, {lng:.6f}
        </div>
        <div class="legend">
            <div class="legend-item"><div class="legend-color" style="background:#00ff00;"></div>起点A</div>
            <div class="legend-item"><div class="legend-color" style="background:#ff0000;"></div>终点B</div>
            <div class="legend-item"><div class="legend-color" style="background:#ff6600;"></div>障碍物</div>
            <div class="legend-item"><div class="legend-line" style="background:#ffff00;"></div>规划航线</div>
        </div>
        
        <script>
            var zoom = {zoom};
            var centerLng = {lng};
            var centerLat = {lat};
            var tileSize = 256;
            
            var mapDiv = document.getElementById('map');
            var mapWidth = window.innerWidth;
            var mapHeight = window.innerHeight;
            mapDiv.style.width = mapWidth + 'px';
            mapDiv.style.height = mapHeight + 'px';
            
            function lngToTileX(lng, zoom) {{
                return Math.floor((lng + 180) / 360 * Math.pow(2, zoom));
            }}
            
            function latToTileY(lat, zoom) {{
                var lat_rad = lat * Math.PI / 180;
                return Math.floor((1 - Math.log(Math.tan(lat_rad) + 1 / Math.cos(lat_rad)) / Math.PI) / 2 * Math.pow(2, zoom));
            }}
            
            function tileToLng(x, zoom) {{
                return x / Math.pow(2, zoom) * 360 - 180;
            }}
            
            function tileToLat(y, zoom) {{
                var n = Math.PI - 2 * Math.PI * y / Math.pow(2, zoom);
                return 180 / Math.PI * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
            }}
            
            var centerTileX = lngToTileX(centerLng, zoom);
            var centerTileY = latToTileY(centerLat, zoom);
            
            var centerTileLng = tileToLng(centerTileX, zoom);
            var centerTileLat = tileToLat(centerTileY, zoom);
            var offsetX = (centerLng - centerTileLng) / 360 * Math.pow(2, zoom) * tileSize;
            var offsetY = (centerTileLat - centerLat) / 360 * Math.pow(2, zoom) * tileSize;
            
            var tilesToRender = 3;
            for (var dy = -tilesToRender; dy <= tilesToRender; dy++) {{
                for (var dx = -tilesToRender; dx <= tilesToRender; dx++) {{
                    var tileX = centerTileX + dx;
                    var tileY = centerTileY + dy;
                    var tileUrl = 'https://webst' + (Math.abs(tileX + tileY) % 4) + '.is.autonavi.com/appmaptile?style=6&x=' + tileX + '&y=' + tileY + '&z=' + zoom;
                    
                    var img = document.createElement('img');
                    img.src = tileUrl;
                    img.style.position = 'absolute';
                    img.style.left = (dx * tileSize - offsetX) + 'px';
                    img.style.top = (dy * tileSize - offsetY) + 'px';
                    img.style.width = tileSize + 'px';
                    img.style.height = tileSize + 'px';
                    img.style.opacity = '1';
                    mapDiv.appendChild(img);
                }}
            }}
            
            function lngLatToPixel(lng, lat) {{
                var x = (lng - centerLng) / 360 * Math.pow(2, zoom) * tileSize + mapWidth/2;
                var y = (centerLat - lat) / 360 * Math.pow(2, zoom) * tileSize + mapHeight/2;
                return {{x: x, y: y}};
            }}
            
            function addMarker(lng, lat, type, name) {{
                var pixel = lngLatToPixel(lng, lat);
                if (pixel.x < -100 || pixel.x > mapWidth + 100 || pixel.y < -100 || pixel.y > mapHeight + 100) return;
                
                var marker = document.createElement('div');
                marker.className = 'marker marker-' + type;
                marker.style.left = pixel.x + 'px';
                marker.style.top = pixel.y + 'px';
                
                var label = document.createElement('div');
                label.className = 'marker-label';
                label.innerText = name;
                marker.appendChild(label);
                
                mapDiv.appendChild(marker);
            }}
            
            function addLine(lng1, lat1, lng2, lat2) {{
                var p1 = lngLatToPixel(lng1, lat1);
                var p2 = lngLatToPixel(lng2, lat2);
                
                var line = document.createElement('div');
                line.style.position = 'absolute';
                line.style.left = Math.min(p1.x, p2.x) + 'px';
                line.style.top = Math.min(p1.y, p2.y) + 'px';
                line.style.width = Math.abs(p2.x - p1.x) + 'px';
                line.style.height = Math.abs(p2.y - p1.y) + 'px';
                line.style.background = '#ffff00';
                line.style.border = '2px solid #ffff00';
                line.style.opacity = '0.8';
                if (p2.x !== p1.x && p2.y !== p1.y) {{
                    var angle = Math.atan2(p2.y - p1.y, p2.x - p1.x) * 180 / Math.PI;
                    line.style.transform = 'rotate(' + angle + 'deg)';
                }}
                mapDiv.appendChild(line);
            }}
            
            setTimeout(function() {{
                // 起点A
                var a_lng = {st.session_state.point_A['lng'] if st.session_state.point_A['set'] else '0'};
                var a_lat = {st.session_state.point_A['lat'] if st.session_state.point_A['set'] else '0'};
                if (a_lng !== 0 && a_lat !== 0) {{
                    addMarker(a_lng, a_lat, 'a', '起点A');
                }}
                
                // 终点B
                var b_lng = {st.session_state.point_B['lng'] if st.session_state.point_B['set'] else '0'};
                var b_lat = {st.session_state.point_B['lat'] if st.session_state.point_B['set'] else '0'};
                if (b_lng !== 0 && b_lat !== 0) {{
                    addMarker(b_lng, b_lat, 'b', '终点B');
                }}
    '''
    
    # 添加障碍物
    for obs in st.session_state.obstacles:
        map_html += f'''
                addMarker({obs['lng']}, {obs['lat']}, 'obstacle', '{obs['name']}');
        '''
    
    # 添加航线
    if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
        a_lng = st.session_state.point_A['lng']
        a_lat = st.session_state.point_A['lat']
        b_lng = st.session_state.point_B['lng']
        b_lat = st.session_state.point_B['lat']
        map_html += f'''
                if (a_lng !== 0 && a_lat !== 0 && b_lng !== 0 && b_lat !== 0) {{
                    addLine({a_lng}, {a_lat}, {b_lng}, {b_lat});
                }}
        '''
    
    map_html += '''
            }}, 100);
            
            window.addEventListener('resize', function() {
                location.reload();
            });
        </script>
    </body>
    </html>
    '''
    
    return map_html

# ============================ 页面配置 ============================

st.set_page_config(page_title="无人机地面站系统", layout="wide")

# ============================ 侧边栏 ============================

st.sidebar.markdown("# 🚁 导航")
page = st.sidebar.radio("功能页面", ["🗺️ 航线规划", "💓 飞行监控"])

st.sidebar.markdown("---")
st.sidebar.markdown("# 📐 坐标系设置")

coord_sys = st.sidebar.selectbox(
    "输入坐标系", ["WGS-84", "GCJ-02(高德/百度)"],
    index=0 if st.session_state.coord_system == "WGS-84" else 1
)
st.session_state.coord_system = coord_sys.split("(")[0]

st.sidebar.markdown("---")
st.sidebar.markdown("# 🗺️ 地图控制")
st.session_state.map_zoom = st.sidebar.slider("缩放级别", 14, 18, st.session_state.map_zoom, 1)

st.sidebar.markdown("---")
st.sidebar.markdown("## 📖 操作说明")
st.sidebar.markdown("- 🟢 **绿色点**: 起点A")
st.sidebar.markdown("- 🔴 **红色点**: 终点B")
st.sidebar.markdown("- 🟠 **橙色点**: 障碍物")
st.sidebar.markdown("- 🟡 **黄线**: 规划航线")
st.sidebar.markdown("- 🛰️ **底图**: 高德卫星影像")

# ============================ 航线规划页面 ============================

if page == "🗺️ 航线规划":
    st.title("🗺️ 航线规划")
    st.markdown("基于高德卫星图的无人机航线规划系统 | 支持 WGS-84 / GCJ-02 坐标系转换")
    
    col1, col2 = st.columns([1, 1.2])
    
    with col1:
        st.markdown("### 🎮 控制面板")
        
        # 起点A
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
        
        # 终点B
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
        
        # 飞行参数
        st.markdown("#### ✈️ 飞行参数")
        st.session_state.flight_height = st.number_input("飞行高度 (m)", value=st.session_state.flight_height, step=5.0)
        
        # 障碍物管理
        st.markdown("#### 🚧 障碍物管理")
        with st.expander("➕ 添加新障碍物", expanded=False):
            obs_name = st.text_input("名称", "新障碍物")
            col_o1, col_o2 = st.columns(2)
            with col_o1:
                obs_lat = st.number_input("纬度", value=32.2330, format="%.6f", key="obs_lat")
            with col_o2:
                obs_lng = st.number_input("经度", value=118.7495, format="%.6f", key="obs_lng")
            obs_radius = st.number_input("半径(m)", value=25, step=5, key="obs_radius")
            if st.button("✅ 确认添加", key="add_obs"):
                st.session_state.obstacles.append({"lat": obs_lat, "lng": obs_lng, "radius": obs_radius, "name": obs_name})
                st.rerun()
    
    with col2:
        st.markdown("### 📊 系统状态")
        
        if st.session_state.point_A["set"]:
            st.success(f"✅ **A点已设**\n📍 {st.session_state.point_A['lat']:.6f}, {st.session_state.point_A['lng']:.6f}")
        else:
            st.warning("❌ **A点未设**")
        
        if st.session_state.point_B["set"]:
            st.success(f"✅ **B点已设**\n📍 {st.session_state.point_B['lat']:.6f}, {st.session_state.point_B['lng']:.6f}")
        else:
            st.warning("❌ **B点未设**")
        
        if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
            dist = calculate_distance(a_lat, a_lng, b_lat, b_lng)
            st.info(f"📏 航线距离: {dist:.1f} 米")
        
        st.info(f"✈️ 飞行高度: {st.session_state.flight_height} m")
        st.info(f"🗺️ 坐标系: {st.session_state.coord_system}")
        
        if st.session_state.obstacles:
            st.markdown("**🚧 障碍物列表**")
            for i, obs in enumerate(st.session_state.obstacles):
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.write(f"{i+1}. {obs['name']} ({obs['radius']}m)")
                    st.caption(f"   {obs['lat']:.6f}, {obs['lng']:.6f}")
                with col_b:
                    if st.button("🗑️", key=f"del_{i}"):
                        st.session_state.obstacles.pop(i)
                        st.rerun()
    
    # 卫星地图显示
    st.markdown("### 🛰️ 高德卫星地图")
    st.markdown("💡 **操作提示**：地图显示真实卫星影像 | 绿色为起点A | 红色为终点B | 橙色为障碍物 | 黄线为航线")
    
    try:
        map_html = get_static_satellite_map()
        st.components.v1.html(map_html, height=550, width=1200, scrolling=False)
    except Exception as e:
        st.error(f"卫星地图加载失败: {str(e)}")
        st.info("请刷新页面重试")

# ============================ 飞行监控页面 ============================

else:
    st.title("🛸 无人机心跳监测系统")
    st.markdown("模拟无人机每秒发送心跳包，3秒未收到自动报警")
    
    if st.session_state.running:
        st.markdown('<meta http-equiv="refresh" content="1">', unsafe_allow_html=True)
    
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
            st.error(f"⚠️ 连接超时！已 {time.time() - st.session_state.last_ts:.1f} 秒未收到心跳")
        else:
            st.success("✅ 连接正常")
    
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.metric("📡 最新心跳序号", st.session_state.seq if st.session_state.seq > 0 else "—")
        status = "✈️ 飞行中" if st.session_state.running else "🛬 已停止"
        st.write(f"**状态: {status}**")
    with col_s2:
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
        df = df.sort_values("时间")
        st.subheader("📈 心跳序号变化趋势")
        st.line_chart(df.set_index("时间")["序号"], use_container_width=True)
        
        df["接收时间"] = df["时间戳"].apply(lambda x: datetime.fromtimestamp(x).strftime("%H:%M:%S"))
        st.subheader("📋 心跳记录（最近20条）")
        st.dataframe(df[["序号", "接收时间"]], use_container_width=True, height=400)
    else:
        st.info("📭 暂无数据，请点击「启动模拟」")

st.markdown("---")
st.markdown("© 2024 无人机地面站系统 | 底图: 高德卫星图 | 支持 WGS-84/GCJ-02 坐标转换 | 实时心跳监测")
