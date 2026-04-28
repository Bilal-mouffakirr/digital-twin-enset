import streamlit as st
import requests
import fmpy
import numpy as np
import pandas as pd
import pvlib
import plotly.graph_objects as go
import os

# --- 1. إعدادات الصفحة ---
st.set_page_config(page_title="PV Digital Twin", page_icon="☀️", layout="wide")
st.title("☀️ التوأم الرقمي لنظام الطاقة الشمسية - المحمدية")
st.markdown("مقارنة لحظية بين نموذج **FMU (MATLAB)** والمحاكاة التحليلية **(pvlib)**.")

# --- 2. جلب بيانات الطقس ---
@st.cache_data(ttl=900)
def get_weather():
    # إحداثيات المحمدية
    url = "https://api.open-meteo.com/v1/forecast?latitude=33.68&longitude=-7.38&current=temperature_2m,shortwave_radiation"
    try:
        resp = requests.get(url).json()
        temp = resp['current']['temperature_2m']
        irr = resp['current']['shortwave_radiation']
        return temp, irr
    except Exception as e:
        st.error(f"خطأ في جلب البيانات: {e}")
        return 25.0, 800.0 # قيم افتراضية

current_temp, current_irr = get_weather()

# عرض الطقس
st.subheader("🌍 البيانات المناخية الحالية (Open-Meteo)")
w_col1, w_col2 = st.columns(2)
w_col1.metric("🌡️ درجة الحرارة", f"{current_temp} °C")
w_col2.metric("☀️ الإشعاع الشمسي", f"{current_irr} W/m²")

st.divider()

# --- 3. محاكاة pvlib ---
def run_pvlib(irr, temp):
    # استخدام معطيات تقريبية للوحة 400 واط بناء على معطياتك
    pdc = pvlib.pvsystem.pvwatts_dc(
        g_poa_effective=irr, 
        temp_cell=temp + 3, # تقريب حرارة الخلية
        pdc0=400, # طاقة اللوحة
        gamma_pdc=-0.004 # معامل الحرارة
    )
    return pdc

pvlib_power = run_pvlib(current_irr, current_temp)

# --- 4. محاكاة FMU ---
fmu_filename = 'PV_MPPT_Inverter1.fmu'
fmu_power, fmu_pondu, fmu_vondu, fmu_rendement = 0, 0, 0, 0

if os.path.exists(fmu_filename):
    try:
        # تحديد المدخلات والمخرجات بناء على ملف XML
        # إذا كانت النتائج غير منطقية، قم بتبديل Inport و Inport1
        input_irr_name = 'Inport' 
        input_temp_name = 'Inport1'
        outputs = ['Ppanneau', 'P_ondu', 'Vonduleur', 'rendemet de onduleur']

        # تجهيز مصفوفة المدخلات
        dtype = [('time', np.float64), (input_irr_name, np.float64), (input_temp_name, np.float64)]
        inputs = np.array([(0.0, current_irr, current_temp), 
                           (1.0, current_irr, current_temp)], dtype=dtype)

        # تشغيل المحاكاة (simulate_fmu تتكفل بالتنظيف التلقائي للذاكرة)
        res = fmpy.simulate_fmu(
            filename=fmu_filename,
            start_time=0.0,
            stop_time=1.0,
            step_size=0.1,
            input=inputs,
            output=outputs
        )

        fmu_power = res['Ppanneau'][-1]
        fmu_pondu = res['P_ondu'][-1]
        fmu_vondu = res['Vonduleur'][-1]
        fmu_rendement = res['rendemet de onduleur'][-1]

    except Exception as e:
        st.error(f"خطأ في تشغيل FMU: {e}")
else:
    st.warning(f"ملف {fmu_filename} غير موجود في المجلد.")

# --- 5. عرض ومقارنة النتائج ---
st.subheader("⚡ نتائج التوأم الرقمي")

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🟢 نموذج MATLAB (FMU)")
    st.metric("طاقة الألواح (DC)", f"{fmu_power:.2f} W")
    st.metric("طاقة العاكس (AC)", f"{fmu_pondu:.2f} W")
    st.metric("جهد العاكس", f"{fmu_vondu:.2f} V")
    st.metric("مردودية العاكس", f"{fmu_rendement:.2f} %")

with col2:
    st.markdown("### 🔵 النموذج التحليلي (pvlib)")
    st.metric("طاقة الألواح (DC المتوقعة)", f"{pvlib_power:.2f} W")
    
    # حساب نسبة الخطأ
    if pvlib_power > 0:
        error = abs(fmu_power - pvlib_power) / pvlib_power * 100
    else:
        error = 0
    st.metric("نسبة الفرق بين النموذجين", f"{error:.1f} %")

st.divider()

# --- 6. الرسوم البيانية (مصلحة من أخطاء الألوان) ---
st.subheader("📊 مقارنة بصرية للطاقة (DC Power)")

fig = go.Figure(data=[
    go.Bar(name='MATLAB (FMU)', x=['الطاقة المنتجة'], y=[fmu_power], marker_color='rgba(46, 204, 113, 0.8)'),
    go.Bar(name='pvlib', x=['الطاقة المنتجة'], y=[pvlib_power], marker_color='rgba(52, 152, 219, 0.8)')
])

fig.update_layout(barmode='group', yaxis_title='الواط (W)', template='plotly_dark')
st.plotly_chart(fig, use_container_width=True)
