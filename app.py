import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
from datetime import datetime

# -------------------------- 页面全局配置 --------------------------
st.set_page_config(
    page_title="无人机智能化应用",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------- 会话状态初始化（关键：跨页面数据共享） --------------------------
if "current_page" not in st.session_state:
    st.session_state.current_page = "航线规划"
if "a_point" not in st.session_state:
    st.session_state.a_point = {"lat": 32.23, "lon": 118.75, "set": False}
if "b_point" not in st.session_state:
    st.session_state.b_point = {"lat": 32.24, "lon": 118.76, "set": False}
if "flight_data" not in st.session_state:
    # 模拟无人机飞行监控数据（可对接真实无人机API）
    st.session_state.flight_data = pd.DataFrame({
        "时间": [datetime.now().strftime("%H:%M:%S")],
        "纬度": [32.235],
        "经度": [118.755],
        "高度(m)": [50.0],
        "速度(m/s)": [3.2],
        "电量(%)": [85],
        "状态": ["正常飞行"]
    })

# -------------------------- 侧边栏（导航+坐标系+状态） --------------------------
with st.sidebar:
    st.header("🚁 导航")
    st.subheader("功能页面")
    
    # 页面切换按钮（核心：保留飞行监控）
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
    
    # 坐标系设置（双页面共享）
    st.subheader("⚙️ 坐标系设置")
    st.write("输入坐标系")
    coord_system = st.radio(
        "",
        ["WGS-84", "GCJ-02(高德/百度)"],
        index=1,
        label_visibility="collapsed"
    )
    
    st.divider()
    
    # 系统状态（双页面共享）
    st.subheader("✅ 系统状态")
    st.write(f"A点状态: {'已设置' if st.session_state.a_point['set'] else '未设置'}")
    st.write(f"B点状态: {'已设置' if st.session_state.b_point['set'] else '未设置'}")
    if st.session_state.current_page == "飞行监控":
        st.write(f"无人机状态: {st.session_state.flight_data.iloc[-1]['状态']}")
        st.write(f"当前电量: {st.session_state.flight_data.iloc[-1]['电量(%)']}%")

# -------------------------- 页面1：航线规划（完全保留你当前的功能） --------------------------
if st.session_state.current_page == "航线规划":
    # 分三栏布局：地图主体 + 右侧控制面板
    col_map, col_ctrl = st.columns([3, 1])

    # 右侧控制面板
    with col_ctrl:
        st.header("⚙️ 控制面板")
        
        # 起点A设置
        st.subheader("📍 起点A")
        a_lat = st.number_input("纬度", value=st.session_state.a_point["lat"], min_value=-90.0, max_value=90.0, step=0.01, key="a_lat")
        a_lon = st.number_input("经度", value=st.session_state.a_point["lon"], min_value=-180.0, max_value=180.0, step=0.01, key="a_lon")
        set_a = st.checkbox("✅ 设置A点", value=st.session_state.a_point["set"], key="set_a")
        
        # 终点B设置
        st.subheader("📍 终点B")
        b_lat = st.number_input("纬度", value=st.session_state.b_point["lat"], min_value=-90.0, max_value=90.0, step=0.01, key="b_lat")
        b_lon = st.number_input("经度", value=st.session_state.b_point["lon"], min_value=-180.0, max_value=180.0, step=0.01, key="b_lon")
        set_b = st.checkbox("✅ 设置B点", value=st.session_state.b_point["set"], key="set_b")
        
        # 更新A/B点状态
        if set_a:
            st.session_state.a_point = {"lat": a_lat, "lon": a_lon, "set": True}
        else:
            st.session_state.a_point["set"] = False
        if set_b:
            st.session_state.b_point = {"lat": b_lat, "lon": b_lon, "set": True}
        else:
            st.session_state.b_point["set"] = False

    # 中间3D地图区域
    with col_map:
        st.header("🗺️ 3D校园地图")
        
        # 底图配置
        if coord_system == "GCJ-02(高德/百度)":
            tile_url = "https://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"
            tile_attr = "&copy; 高德地图"
            center_lat, center_lon = st.session_state.a_point["lat"], st.session_state.a_point["lon"]
        else:
            tile_url = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            tile_attr = "&copy; OpenStreetMap contributors"
            center_lat, center_lon = st.session_state.a_point["lat"], st.session_state.a_point["lon"]
        
        # 地图初始化
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=17,
            tiles=tile_url,
            attr=tile_attr,
            control_scale=True,
            prefer_canvas=True
        )
        
        # 标记A/B点+航线
        if st.session_state.a_point["set"]:
            folium.Marker(
                location=[st.session_state.a_point["lat"], st.session_state.a_point["lon"]],
                popup="起点A",
                icon=folium.Icon(color="red", icon="map-marker")
            ).add_to(m)
        if st.session_state.b_point["set"]:
            folium.Marker(
                location=[st.session_state.b_point["lat"], st.session_state.b_point["lon"]],
                popup="终点B",
                icon=folium.Icon(color="blue", icon="map-marker")
            ).add_to(m)
            # 绘制A-B航线
            if st.session_state.a_point["set"]:
                folium.PolyLine(
                    locations=[
                        [st.session_state.a_point["lat"], st.session_state.a_point["lon"]],
                        [st.session_state.b_point["lat"], st.session_state.b_point["lon"]]
                    ],
                    color="green",
                    weight=3,
                    opacity=0.8
                ).add_to(m)
        
        # 渲染地图
        st_folium(m, width="100%", height=600, key="route_map")

# -------------------------- 页面2：飞行监控（完整保留+功能增强） --------------------------
elif st.session_state.current_page == "飞行监控":
    st.header("📡 无人机飞行监控")
    
    # 分栏布局：地图 + 实时数据面板
    col_map, col_data = st.columns([2, 1])
    
    # 左侧：实时飞行轨迹地图
    with col_map:
        st.subheader("🗺️ 实时飞行轨迹")
        
        # 底图配置（和航线规划页一致）
        if coord_system == "GCJ-02(高德/百度)":
            tile_url = "https://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"
            tile_attr = "&copy; 高德地图"
        else:
            tile_url = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            tile_attr = "&copy; OpenStreetMap contributors"
        
        # 以无人机最新位置为中心
        latest = st.session_state.flight_data.iloc[-1]
        m = folium.Map(
            location=[latest["纬度"], latest["经度"]],
            zoom_start=17,
            tiles=tile_url,
            attr=tile_attr,
            control_scale=True
        )
        
        # 绘制历史飞行轨迹
        folium.PolyLine(
            locations=st.session_state.flight_data[["纬度", "经度"]].values.tolist(),
            color="red",
            weight=2,
            opacity=0.7
        ).add_to(m)
        
        # 标记当前无人机位置
        folium.Marker(
            location=[latest["纬度"], latest["经度"]],
            popup=f"当前位置\n高度: {latest['高度(m)']}m\n速度: {latest['速度(m/s)']}m/s",
            icon=folium.Icon(color="green", icon="plane")
        ).add_to(m)
        
        # 渲染地图
        st_folium(m, width="100%", height=500, key="flight_map")
        
        # 模拟数据更新按钮（对接真实无人机时可删除）
        if st.button("🔄 更新飞行数据", use_container_width=True):
            # 模拟无人机位置移动、电量下降
            new_row = {
                "时间": datetime.now().strftime("%H:%M:%S"),
                "纬度": latest["纬度"] + 0.0001,
                "经度": latest["经度"] + 0.0001,
                "高度(m)": round(latest["高度(m)"] + 0.5, 1),
                "速度(m/s)": round(latest["速度(m/s)"] + 0.1, 1),
                "电量(%)": max(latest["电量(%)"] - 1, 0),
                "状态": "正常飞行" if latest["电量(%)"] > 20 else "低电量告警"
            }
            st.session_state.flight_data = pd.concat([st.session_state.flight_data, pd.DataFrame([new_row])], ignore_index=True)
            st.rerun()
    
    # 右侧：实时数据面板
    with col_data:
        st.subheader("📊 实时参数")
        # 显示最新数据
        latest = st.session_state.flight_data.iloc[-1]
        
        # 关键指标卡片
        col1, col2 = st.columns(2)
        with col1:
            st.metric(label="📏 高度(m)", value=latest["高度(m)"])
            st.metric(label="🔋 电量(%)", value=latest["电量(%)"], delta=f"-{1}%")
        with col2:
            st.metric(label="⚡ 速度(m/s)", value=latest["速度(m/s)"])
            st.metric(label="📍 状态", value=latest["状态"])
        
        st.divider()
        
        # 详细坐标信息
        st.subheader("📍 当前位置")
        st.write(f"纬度: {latest['纬度']:.4f}")
        st.write(f"经度: {latest['经度']:.4f}")
        st.write(f"坐标系: {coord_system}")
        
        st.divider()
        
        # 历史数据表格
        st.subheader("📋 飞行历史")
        st.dataframe(st.session_state.flight_data, use_container_width=True, hide_index=True)

# -------------------------- 依赖说明（Streamlit Cloud自动安装） --------------------------
# requirements.txt 内容：
# streamlit==1.35.0
# folium==0.16.0
# streamlit-folium==0.17.0
# pandas==2.2.2
