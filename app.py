import streamlit as st
import requests
import fmpy
import numpy as np
import pandas as pd
import pvlib
import plotly.graph_objects as go
import os

# ==========================================
# 1. إعدادات الصفحة الأساسية
# ==========================================
st.set_page_config(page_title="Digital Twin | PV System", page_icon="☀️", layout="wide", initial_sidebar_state="expanded")

# تصميم إضافي بالـ CSS لتجميل الواجهة
st.markdown("""
    <style>
    .main-header {font-size: 2.5rem; color: #2E86C1; text-align: center; font-weight: bold;}
    .sub-header {text-align: center; color: #7F8C8D; margin-bottom: 2rem;}
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">☀️ التوأم الرقمي الذكي - محطة المحمدية</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">مراقبة ومقارنة الأداء الفعلي (FMU) مع النموذج التحليلي (pvlib) في الوقت الفعلي</div>', unsafe_allow_html=True)

# ==========================================
# 2. جلب البيانات من Open-Meteo
# ==========================================
@st.cache_data(ttl=900)
def fetch_weather_data():
    url = "https://api.open-meteo.com/v1/forecast?latitude=33.68&longitude=-7.38&current=temperature_2m,shortwave_radiation"
    try:
        resp = requests.get(url).json()
        return resp['current']['temperature_2m'], resp['current']['shortwave_radiation']
    except:
        return 25.0, 800.0 # قيم افتراضية للحماية من الأخطاء

temp_c, irradiance_w = fetch_weather_data()

# ==========================================
# 3. النماذج الحسابية (pvlib و FMU)
# ==========================================
# أ. نموذج pvlib (المرجعي)
def calculate_pvlib(g_poa, temp):
    pdc = pvlib.pvsystem.pvwatts_dc(
        g_poa_effective=g_poa, 
        temp_cell=temp + 3, 
        pdc0=400, # قدرة اللوحة
        gamma_pdc=-0.004
    )
    return pdc

pvlib_dc_power = calculate_pvlib(irradiance_w, temp_c)

# ب. نموذج FMU (الماتلاب)
fmu_filename = 'PV_MPPT_Inverter1.fmu'
fmu_dc_power, fmu_ac_power, fmu_ac_voltage, fmu_efficiency = 0.0, 0.0, 0.0, 0.0

if os.path.exists(fmu_filename):
    try:
        inputs = np.array([(0.0, irradiance_w, temp_c), (1.0, irradiance_w, temp_c)], 
                          dtype=[('time', np.float64), ('Inport', np.float64), ('Inport1', np.float64)])
        
        outputs = ['Ppanneau', 'P_ondu', 'Vonduleur', 'rendemet de onduleur']
        
        res = fmpy.simulate_fmu(
            filename=fmu_filename, start_time=0.0, stop_time=1.0, step_size=0.1,
            input=inputs, output=outputs
        )
        
        fmu_dc_power = res['Ppanneau'][-1]
        fmu_ac_power = res['P_ondu'][-1]
        fmu_ac_voltage = res['Vonduleur'][-1]
        fmu_efficiency = res['rendemet de onduleur'][-1]
    except Exception as e:
        st.error(f"⚠️ مشكل في تشغيل FMU: {e}")
else:
    st.error("⚠️ ملف FMU غير موجود! يرجى رفعه إلى GitHub.")

# ==========================================
# 4. بناء واجهة العرض (Dashboard UI)
# ==========================================
tab1, tab2 = st.tabs(["🌍 لوحة القيادة الرئيسية", "⚙️ تفاصيل النظام"])

with tab1:
    # --- قسم الطقس ---
    st.markdown("### 🌤️ البيانات المناخية الحالية")
    w1, w2, w3 = st.columns(3)
    w1.metric("المدينة", "المحمدية, المغرب")
    w2.metric("درجة الحرارة", f"{temp_c} °C")
    w3.metric("الإشعاع الشمسي (GHI)", f"{irradiance_w} W/m²")
    
    st.divider()

    # --- قسم المقارنة الرئيسية ---
    st.markdown("### ⚡ مقارنة طاقة الألواح (DC Power)")
    c1, c2, c3 = st.columns(3)
    
    c1.metric("طاقة FMU (ماتلاب)", f"{fmu_dc_power:.2f} W", delta="Live", delta_color="normal")
    c2.metric("طاقة pvlib (المرجعية)", f"{pvlib_dc_power:.2f} W", delta="Reference", delta_color="off")
    
    error_pct = abs(fmu_dc_power - pvlib_dc_power) / pvlib_dc_power * 100 if pvlib_dc_power > 0 else 0
    c3.metric("نسبة الفرق (Error)", f"{error_pct:.2f} %", delta="- دقة الموديل", delta_color="inverse")

    # --- المبيانات (Charts) ---
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.markdown("#### 📊 مقارنة الإنتاجية")
        fig_bar = go.Figure([
            go.Bar(name='FMU (MATLAB)', x=['الطاقة (DC)'], y=[fmu_dc_power], marker_color='#2ecc71'),
            go.Bar(name='pvlib (Analytic)', x=['الطاقة (DC)'], y=[pvlib_dc_power], marker_color='#3498db')
        ])
        fig_bar.update_layout(barmode='group', template='plotly_dark', height=300, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_chart2:
        st.markdown("#### ⚙️ مردودية العاكس (Inverter Efficiency)")
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = fmu_efficiency,
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': "الكفاءة %"},
            gauge = {
                'axis': {'range': [None, 100]},
                'bar': {'color': "#f39c12"},
                'steps' : [
                    {'range': [0, 50], 'color': "rgba(231, 76, 60, 0.3)"},
                    {'range': [50, 80], 'color': "rgba(241, 196, 15, 0.3)"},
                    {'range': [80, 100], 'color': "rgba(46, 204, 113, 0.3)"}],
            }
        ))
        fig_gauge.update_layout(height=300, margin=dict(l=20, r=20, t=30, b=20), template='plotly_dark')
        st.plotly_chart(fig_gauge, use_container_width=True)

with tab2:
    st.markdown("### 🔌 المخرجات الكهربائية للعاكس (AC Outputs - FMU)")
    ac1, ac2, ac3 = st.columns(3)
    ac1.info(f"**طاقة العاكس (P_ondu):** \n\n ### {fmu_ac_power:.2f} W")
    ac2.success(f"**جهد العاكس (Vonduleur):** \n\n ### {fmu_ac_voltage:.2f} V")
    ac3.warning(f"**حالة الاتصال:** \n\n ### متصل بالشبكة ✅")
