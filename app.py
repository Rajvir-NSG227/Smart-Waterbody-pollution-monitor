import streamlit as st
import pandas as pd
import requests
import time
import os
import smtplib
import ssl
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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
st.markdown(
    """
    <style>
        @keyframes blinker { 50% { opacity: 0; } }
        .live-dot {
            width: 10px;
            height: 10px;
            background-color: #00ff88;
            border-radius: 50%;
            display: inline-block;
            animation: blinker 1.2s ease-in-out infinite;
            margin-right: 8px;
            box-shadow: 0 0 6px #00ff88;
            flex-shrink: 0;
        }
        .live-badge {
            position: fixed !important;
            bottom: 60px !important; 
            right: 18px !important;
            z-index: 999999 !important;
            display: flex !important;
            align-items: center !important;
            padding: 6px 14px !important;
            background: rgba(10, 20, 30, 0.92) !important;
            backdrop-filter: blur(8px) !important;
            -webkit-backdrop-filter: blur(8px) !important;
            border: 1px solid rgba(0, 255, 136, 0.4) !important;
            border-radius: 20px !important;
            box-shadow: 0 2px 12px rgba(0,255,136,0.15) !important;
            pointer-events: none !important;
        }
        .live-badge span.live-text {
            font-size: 0.78rem !important;
            color: #00ff88 !important;
            font-weight: 600 !important;
            letter-spacing: 0.5px !important;
            font-family: 'Inter', sans-serif !important;
        }
    </style>
    <div class="live-badge">
        <span class="live-dot"></span>
        <span class="live-text">LIVE &nbsp;·&nbsp; Node-1</span>
    </div>
    """,
    unsafe_allow_html=True
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

# ── Email credentials loaded securely from .streamlit/secrets.toml ──
try:
    EMAIL_SENDER   = st.secrets.get("EMAIL_SENDER",   "")
    EMAIL_PASSWORD = st.secrets.get("EMAIL_PASSWORD", "")
    EMAIL_RECEIVER = st.secrets.get("EMAIL_RECEIVER", "")
except Exception:
    EMAIL_SENDER = EMAIL_PASSWORD = EMAIL_RECEIVER = ""
EMAIL_SENDER   = EMAIL_SENDER   or os.getenv("EMAIL_SENDER",   "")
EMAIL_PASSWORD = EMAIL_PASSWORD or os.getenv("EMAIL_PASSWORD", "")
EMAIL_RECEIVER = EMAIL_RECEIVER or os.getenv("EMAIL_RECEIVER", "")

# Alert cooldown: minimum minutes between successive email alerts
EMAIL_COOLDOWN_MINUTES = 15

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
# 6b. EMAIL ALERT
# ─────────────────────────────────────────────
def send_email_alert(anomalies: dict) -> bool:
    """
    Send an HTML email listing all anomalous parameters.
    Returns True on success, False on failure.
    """
    if not (EMAIL_SENDER and EMAIL_PASSWORD and EMAIL_RECEIVER):
        return False

    timestamp = datetime.now().strftime("%d %B %Y, %I:%M:%S %p")

    # ── Build HTML rows for each anomaly ──
    rows_html = ""
    for param, info in anomalies.items():
        excess = info['value'] - info['threshold']
        rows_html += f"""
        <tr>
          <td style='padding:10px 16px; font-weight:600; color:#e0e0e0;'>{param}</td>
          <td style='padding:10px 16px; color:#ff6b6b; font-weight:700;'>
            {info['value']:.2f} {info['unit']}
          </td>
          <td style='padding:10px 16px; color:#8899aa;'>
            {info['threshold']} {info['unit']}
          </td>
          <td style='padding:10px 16px; color:#ffa07a; font-weight:600;'>
            +{excess:.2f} {info['unit']}
          </td>
        </tr>"""

    html_body = f"""\
    <html><body style='margin:0; padding:0; background:#0d1117; font-family:Inter,Arial,sans-serif;'>
      <div style='max-width:600px; margin:30px auto; background:#161b22;
                  border-radius:14px; overflow:hidden;
                  border:1px solid rgba(255,80,80,0.3);'>

        <!-- Header -->
        <div style='background:linear-gradient(135deg,#1a0000,#3d0000);
                    padding:28px 32px; text-align:center;'>
          <h1 style='margin:0; color:#ff6b6b; font-size:1.6rem;'>⚠️ Water Quality Alert</h1>
          <p style='margin:6px 0 0; color:#cc8888; font-size:0.9rem;'>
            Smart Waterbody Pollution Monitor — Telibandha Lake, Raipur
          </p>
        </div>

        <!-- Body -->
        <div style='padding:28px 32px;'>
          <p style='color:#ccddee; margin-top:0;'>
            The IoT monitoring buoy has detected <b style='color:#ff6b6b;'>
            {len(anomalies)} anomalous parameter(s)</b> that exceed safe thresholds.
            Immediate attention may be required.
          </p>

          <!-- Table -->
          <table style='width:100%; border-collapse:collapse; margin:16px 0;
                        background:#0d1117; border-radius:10px; overflow:hidden;'>
            <thead>
              <tr style='background:#1f2937;'>
                <th style='padding:10px 16px; text-align:left; color:#8899aa;
                           font-size:0.8rem; letter-spacing:1px;'>PARAMETER</th>
                <th style='padding:10px 16px; text-align:left; color:#8899aa;
                           font-size:0.8rem; letter-spacing:1px;'>MEASURED</th>
                <th style='padding:10px 16px; text-align:left; color:#8899aa;
                           font-size:0.8rem; letter-spacing:1px;'>SAFE LIMIT</th>
                <th style='padding:10px 16px; text-align:left; color:#8899aa;
                           font-size:0.8rem; letter-spacing:1px;'>EXCESS</th>
              </tr>
            </thead>
            <tbody>{rows_html}</tbody>
          </table>

          <p style='color:#8899aa; font-size:0.85rem; margin-bottom:0;'>
            🕐 Detected at: <b style='color:#aabbcc;'>{timestamp}</b>
          </p>
        </div>

        <!-- Footer -->
        <div style='background:#0d1117; padding:16px 32px; text-align:center;
                    border-top:1px solid #21262d;'>
          <p style='color:#4a5568; font-size:0.78rem; margin:0;'>
            Sent automatically by Smart Waterbody Monitor · Do not reply to this email
          </p>
        </div>
      </div>
    </body></html>"""

    subject = (
        f"⚠️ WATER ALERT — "
        + ", ".join(
            f"{p}: {i['value']:.1f} {i['unit']}" for p, i in anomalies.items()
        )
        + " | Telibandha Lake"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Smart Water Monitor <{EMAIL_SENDER}>"
    msg["To"]      = EMAIL_RECEIVER
    msg.attach(MIMEText(html_body, "html"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        return True
    except Exception as e:
        st.warning(f"📧 Email alert failed: {e}")
        return False

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
            model="gemini-3.5-flash-lite",
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
        anomalies['Turbidity'] = {
            'value': turb_val, 'threshold': TURBIDITY_THRESHOLD, 'unit': 'NTU'
        }

    if tds_val > TDS_THRESHOLD:
        st.error(f"💧 HIGH TDS: {tds_val:.1f} ppm  (threshold: {TDS_THRESHOLD} ppm)")
        anomalies['TDS'] = {
            'value': tds_val, 'threshold': TDS_THRESHOLD, 'unit': 'ppm'
        }

    # ── Send Telegram alert for ALL anomalies (fixed: now includes Temperature) ──
    if anomalies and not alert_sent:
        alert_parts = ", ".join(
            f"{p}: {i['value']:.1f} {i['unit']}" for p, i in anomalies.items()
        )
        send_telegram_alert(
            f"⚠️ WATER ALERT at Telibandha Lake!\n{alert_parts}"
        )
        alert_sent = True

    # ── Send Email alert with cooldown ────────────────────────────────────────
    if anomalies:
        # Initialise session state for cooldown tracking
        if "last_email_sent" not in st.session_state:
            st.session_state.last_email_sent = None

        now = datetime.now()
        cooldown_ok = (
            st.session_state.last_email_sent is None
            or now - st.session_state.last_email_sent
               >= timedelta(minutes=EMAIL_COOLDOWN_MINUTES)
        )

        if cooldown_ok:
            email_ok = send_email_alert(anomalies)
            if email_ok:
                st.session_state.last_email_sent = now
                st.toast(
                    f"📧 Email alert sent to {EMAIL_RECEIVER}!",
                    icon="✅"
                )
        else:
            minutes_left = EMAIL_COOLDOWN_MINUTES - int(
                (now - st.session_state.last_email_sent).total_seconds() / 60
            )
            st.caption(
                f"📧 Next email alert in ≈ {minutes_left} min "
                f"(cooldown: {EMAIL_COOLDOWN_MINUTES} min)"
            )

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

        # Initialize session state for AI suggestion
        if "ai_suggestion" not in st.session_state:
            st.session_state.ai_suggestion = None
        if "ai_suggestion_time" not in st.session_state:
            st.session_state.ai_suggestion_time = None

        col_btn1, col_btn2 = st.columns([3, 1])
        with col_btn1:
            if st.button(
                "🤖 Get AI Cleaning Suggestions",
                type="primary",
                use_container_width=True,
                key="ai_btn"
            ):
                with st.spinner(
                    "🧠 Gemini AI is analysing water conditions and generating a remediation plan..."
                ):
                    st.session_state.ai_suggestion = get_ai_cleaning_suggestions(anomalies)
                    st.session_state.ai_suggestion_time = time.strftime('%H:%M:%S, %d %B %Y')

        with col_btn2:
            if st.session_state.ai_suggestion:
                if st.button("🗑️ Clear", use_container_width=True, key="ai_clear_btn"):
                    st.session_state.ai_suggestion = None
                    st.session_state.ai_suggestion_time = None
                    st.rerun()

        # Display persisted suggestion
        if st.session_state.ai_suggestion:
            # Styled AI header banner
            st.markdown("""
            <div class="ai-panel">
                <div class="ai-header">
                    <span style="font-size:1.5rem;">🤖</span>
                    <span style="color:#00d4aa; font-size:1.2rem; font-weight:700;">
                        AI Remediation Report
                    </span>
                    <span class="ai-badge">Gemini 3.5 Flash Lite</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Render AI output (markdown-aware)
            st.info("📋 **AI-Generated Remediation Plan** — Tailored to live sensor anomalies")
            st.markdown(st.session_state.ai_suggestion)
            st.caption(
                f"⏱️ Generated at {st.session_state.ai_suggestion_time} | "
                "Powered by Google Gemini AI"
            )
    else:
        # Clear suggestion if anomalies are resolved
        if "ai_suggestion" in st.session_state:
            st.session_state.ai_suggestion = None
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