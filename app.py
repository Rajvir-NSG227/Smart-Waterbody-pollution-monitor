import streamlit as st
import pandas as pd
import requests
import time
import os
from google import genai
import folium
from streamlit_folium import st_folium

# ─────────────────────────────────────────────
# 1. PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Smart Waterbody Monitor",
    page_icon="🌊",
    layout="wide"
)

# ─────────────────────────────────────────────
# 2. CUSTOM CSS — Premium Dark Theme
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.ai-panel {
    background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
    border: 1px solid #00d4aa33;
    border-radius: 16px;
    padding: 24px;
    margin-top: 16px;
    box-shadow: 0 8px 32px rgba(0, 212, 170, 0.1);
}
.ai-panel h3 { color: #00d4aa; margin-bottom: 8px; font-size: 1.3rem; }

.ai-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid #00d4aa33;
}
.ai-badge {
    background: linear-gradient(90deg, #00d4aa, #00a8ff);
    color: #000;
    font-size: 0.7rem;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 20px;
    letter-spacing: 1px;
    text-transform: uppercase;
}
.anomaly-chip {
    display: inline-block;
    background: rgba(255, 80, 80, 0.15);
    border: 1px solid rgba(255, 80, 80, 0.4);
    border-radius: 20px;
    padding: 4px 14px;
    margin: 4px 4px 4px 0;
    font-size: 0.82rem;
    color: #ff7070;
    font-weight: 600;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# 3. CONFIGURATION
# ─────────────────────────────────────────────
THINGSPEAK_CHANNEL_ID = "3462165"

# ── Telegram credentials loaded securely from .streamlit/secrets.toml ──
try:
    TELEGRAM_BOT_TOKEN = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID   = st.secrets.get("TELEGRAM_CHAT_ID", "")
except Exception:
    TELEGRAM_BOT_TOKEN = ""
    TELEGRAM_CHAT_ID   = ""
TELEGRAM_BOT_TOKEN = TELEGRAM_BOT_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = TELEGRAM_CHAT_ID   or os.getenv("TELEGRAM_CHAT_ID", "")

# Anomaly Thresholds
TURBIDITY_THRESHOLD   = 50      # NTU
TDS_THRESHOLD         = 400     # ppm
TEMPERATURE_THRESHOLD = 40      # °C

# Sensor location (Raipur – Telibandha Lake)
SENSOR_LAT = 21.239528
SENSOR_LON = 81.659694

try:
    GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
except Exception:
    GEMINI_API_KEY = ""
GEMINI_API_KEY = GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
# ─────────────────────────────────────────────
# 4. HEADER
# ─────────────────────────────────────────────
st.markdown("""
<h1 style='text-align:center; background: linear-gradient(90deg, #00d4aa, #00a8ff);
-webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size:2.4rem; margin-bottom:0;'>
🌊 Smart Waterbody Pollution Monitor
</h1>
<p style='text-align:center; color:#8899aa; margin-top:4px;'>
Real-time Sensor Data · Trend Analysis · Anomaly Detection
</p>
""", unsafe_allow_html=True)
st.markdown("---")
st.markdown("### 📋 Alert Thresholds")
st.markdown(f"🌡️ Temperature > **{TEMPERATURE_THRESHOLD} °C**")
st.markdown(f"🌫️ Turbidity > **{TURBIDITY_THRESHOLD} NTU**")
st.markdown(f"💧 TDS > **{TDS_THRESHOLD} ppm**")
st.markdown("---")
st.caption("Auto-refreshes every 120 seconds")

# ─────────────────────────────────────────────
# 5. FETCH DATA FROM THINGSPEAK
# ─────────────────────────────────────────────
@st.cache_data(ttl=120)
def fetch_data():
    url = f"https://api.thingspeak.com/channels/{THINGSPEAK_CHANNEL_ID}/feeds.json?results=30"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            df = pd.DataFrame(data['feeds'])
            if not df.empty:
                df = df.rename(columns={
                    'created_at': 'Time',
                    'field1': 'Temperature (°C)',
                    'field2': 'Turbidity (NTU)',
                    'field3': 'TDS (ppm)'
                })
                df['Temperature (°C)'] = pd.to_numeric(df['Temperature (°C)'], errors='coerce')
                df['Turbidity (NTU)']   = pd.to_numeric(df['Turbidity (NTU)'],   errors='coerce')
                df['TDS (ppm)']         = pd.to_numeric(df['TDS (ppm)'],         errors='coerce')
                return df
    except Exception as e:
        st.warning(f"Failed to fetch data: {e}")
    return pd.DataFrame()

# ─────────────────────────────────────────────
# 6. TELEGRAM ALERT
# ─────────────────────────────────────────────
def send_telegram_alert(message):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url = (
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
            f"/sendMessage?chat_id={TELEGRAM_CHAT_ID}&text={message}"
        )
        try:
            requests.get(url, timeout=5)
        except Exception:
            pass

# ─────────────────────────────────────────────
# 7. GEMINI AI — Waterbody Cleaning Suggestions
# ─────────────────────────────────────────────
def get_ai_cleaning_suggestions(anomalies: dict) -> str:
    """
    anomalies: dict of {
        'Parameter Name': {'value': float, 'threshold': float, 'unit': str}
    }
    Returns AI-generated remediation suggestions as a markdown string.
    """
    if not GEMINI_API_KEY:
        return (
            "⚠️ **Gemini API key not set.**\n\n"
        )

    try:
        # New google-genai SDK: use Client object
        client = genai.Client(api_key=GEMINI_API_KEY)

        # Build a detailed, expert-level prompt
        anomaly_lines = "\n".join([
            f"  • **{param}**: {info['value']:.2f} {info['unit']} "
            f"(safe threshold: ≤ {info['threshold']} {info['unit']})"
            for param, info in anomalies.items()
        ])

        prompt = f"""You are a senior environmental scientist and waterbody remediation expert.

A real-time IoT monitoring buoy has detected the following **abnormally high** water quality parameters in a freshwater lake:

{anomaly_lines}

Based on these specific anomalies, provide a structured remediation report with these sections:

### 1. 🔍 Likely Causes
What environmental, industrial, or biological factors could cause each parameter to exceed its safe threshold?

### 2. 🚨 Immediate Actions (0–48 hours)
Emergency steps that lake authorities should take right now to prevent further deterioration.

### 3. 🧹 Cleaning & Remediation Methods
Specific, practical, and proven techniques to bring each elevated parameter back within safe limits.
Include both physical methods (e.g., aeration, skimming), biological methods (e.g., bioremediation, algae control), and chemical methods (e.g., coagulation, flocculation) as appropriate.

### 4. 🛡️ Long-term Preventive Measures
Sustainable strategies to prevent recurrence of these anomalies.

Keep the response practical, concise, and directly tied to the specific parameters listed. Use bullet points.
"""

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt
        )
        return response.text

    except Exception as e:
        return (
            f"❌ **Gemini API Error:** {str(e)}\n\n"
            "Please verify your API key is correct and has available quota.\n"
            "Get a key at: https://aistudio.google.com/app/apikey"
        )

# ─────────────────────────────────────────────
# 9. MAIN DASHBOARD
# ─────────────────────────────────────────────
df = fetch_data()

if not df.empty:
    latest = df.iloc[-1]

    temp_val = latest['Temperature (°C)']
    turb_val = latest['Turbidity (NTU)']
    tds_val  = latest['TDS (ppm)']

    # ── Current Readings ──────────────────────
    st.subheader("💧 Current Water Quality Readings")
    c1, c2, c3 = st.columns(3)

    c1.metric(
        "🌡️ Temperature",
        f"{temp_val:.1f} °C",
        delta=f"{temp_val - TEMPERATURE_THRESHOLD:+.1f} vs limit" if temp_val > TEMPERATURE_THRESHOLD else None,
        delta_color="inverse"
    )
    c2.metric(
        "🌫️ Turbidity",
        f"{turb_val:.1f} NTU",
        delta=f"{turb_val - TURBIDITY_THRESHOLD:+.1f} vs limit" if turb_val > TURBIDITY_THRESHOLD else None,
        delta_color="inverse"
    )
    c3.metric(
        "💧 TDS",
        f"{tds_val:.1f} ppm",
        delta=f"{tds_val - TDS_THRESHOLD:+.1f} vs limit" if tds_val > TDS_THRESHOLD else None,
        delta_color="inverse"
    )

    st.markdown("---")

    # ── Anomaly Detection ─────────────────────
    st.subheader("⚠️ Anomaly Detection")
    anomalies = {}      # Collect all triggered anomalies
    alert_sent = False

    if temp_val > TEMPERATURE_THRESHOLD:
        st.error(f"🌡️ HIGH TEMPERATURE: {temp_val:.1f} °C  (threshold: {TEMPERATURE_THRESHOLD} °C)")
        anomalies['Temperature'] = {
            'value': temp_val, 'threshold': TEMPERATURE_THRESHOLD, 'unit': '°C'
        }

    if turb_val > TURBIDITY_THRESHOLD:
        st.error(f"🌫️ HIGH TURBIDITY: {turb_val:.1f} NTU  (threshold: {TURBIDITY_THRESHOLD} NTU)")
        if not alert_sent:
            send_telegram_alert(
                f"⚠️ WATER ALERT: High Turbidity ({turb_val:.1f} NTU) at Telibandha Lake!"
            )
            alert_sent = True
        anomalies['Turbidity'] = {
            'value': turb_val, 'threshold': TURBIDITY_THRESHOLD, 'unit': 'NTU'
        }

    if tds_val > TDS_THRESHOLD:
        st.error(f"💧 HIGH TDS: {tds_val:.1f} ppm  (threshold: {TDS_THRESHOLD} ppm)")
        if not alert_sent:
            send_telegram_alert(
                f"⚠️ WATER ALERT: High TDS ({tds_val:.1f} ppm) at Telibandha Lake!"
            )
            alert_sent = True
        anomalies['TDS'] = {
            'value': tds_val, 'threshold': TDS_THRESHOLD, 'unit': 'ppm'
        }

    if not anomalies:
        st.success("✅ All parameters are within normal range. Waterbody is healthy.")

    st.markdown("---")
        
    # ── 🤖 AI Remediation Advisor ─────────────
    st.subheader("🤖 AI Remediation Advisor")

    if anomalies:
        # Show abnormal parameters as styled chips
        chips_html = "".join([
            f"<span class='anomaly-chip'>⚠️ {p}: {info['value']:.1f} {info['unit']}</span>"
            for p, info in anomalies.items()
        ])
        st.markdown(
            "<p style='color:#aabbcc; margin-bottom:6px;'>"
            "The following parameters are above safe thresholds:</p>"
            + chips_html,
            unsafe_allow_html=True
        )
        st.markdown(" ")

        if st.button(
            "🤖 Get AI Cleaning Suggestions",
            type="primary",
            use_container_width=True,
            key="ai_btn"
        ):
            with st.spinner(
                "🧠 Gemini AI is analysing water conditions and generating a remediation plan..."
            ):
                suggestion = get_ai_cleaning_suggestions(anomalies)

            # Styled AI header banner
            st.markdown("""
            <div class="ai-panel">
                <div class="ai-header">
                    <span style="font-size:1.5rem;">🤖</span>
                    <span style="color:#00d4aa; font-size:1.2rem; font-weight:700;">
                        AI Remediation Report
                    </span>
                    <span class="ai-badge">Gemini 3.6 Flash</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Render AI output (markdown-aware)
            st.info("📋 **AI-Generated Remediation Plan** — Tailored to live sensor anomalies")
            st.markdown(suggestion)
            st.caption(
                f"⏱️ Generated at {time.strftime('%H:%M:%S, %d %B %Y')} | "
                "Powered by Google Gemini AI"
            )
    else:
        st.markdown("""
        <div style='background:rgba(0,212,170,0.06); border:1px solid rgba(0,212,170,0.2);
        border-radius:12px; padding:20px; text-align:center; color:#00d4aa;'>
            ✅ <b>No anomalies detected.</b><br>
            <span style='color:#8899aa; font-size:0.9rem;'>
            AI suggestions will appear here when any parameter exceeds its safe threshold.
            </span>
        </div>
        """, unsafe_allow_html=True)


    st.markdown("---")
    
    # ── Sensor Map ─────────────────────────────
    st.subheader("📍 Sensor Deployment Location")
    anomaly_detected = bool(anomalies)
    status_color = "red" if anomaly_detected else "green"
    status_text  = "⚠️ ALERT: Anomaly Detected" if anomaly_detected else "✅ Normal"

    m = folium.Map(location=[SENSOR_LAT, SENSOR_LON], zoom_start=16)
    folium.Marker(
        [SENSOR_LAT, SENSOR_LON],
        popup=f"Buoy Node-1\nStatus: {status_text}",
        tooltip="🌊 Smart Waterbody Sensor — Click for details",
        icon=folium.Icon(color=status_color, icon="info-sign")
    ).add_to(m)
    st_folium(m, width=800, height=400)
    st.markdown("---")

    # Download CSV
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Download Data Report (CSV)", csv, "water_quality_report.csv", "text/csv")

    st.markdown("---")

    # ── Trend Analysis ─────────────────────────────

    st.subheader("📈 Trend Analysis")
    df_chart = df.set_index('Time')

    t1, t2, t3 = st.tabs(["🌡️ Temperature", "🌫️ Turbidity", "💧 TDS"])
    with t1:
        st.line_chart(df_chart[['Temperature (°C)']])
    with t2:
        st.line_chart(df_chart[['Turbidity (NTU)']])
    with t3:
        st.line_chart(df_chart[['TDS (ppm)']])

else:
    st.warning(
        "⏳ Fetching data from ThingSpeak... "
        "Please check your Channel ID or wait for the ESP32 to send data.")
# ─────────────────────────────────────────────
# Auto-refresh every 120 seconds
# ─────────────────────────────────────────────
time.sleep(120)
st.rerun()