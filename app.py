import streamlit as st
import google.generativeai as genai
import json
import os
from PIL import Image
from datetime import datetime
import requests
import base64
from io import BytesIO

# --- 1. FUNGSI PEMBACA FILE EKSTERNAL ---
def load_json_file(file_path, default_value):
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return json.load(f)
    return default_value

# --- 2. KONFIGURASI UI & SESSION STATE ---
st.set_page_config(page_title="Wyckoff Modular Brain", layout="wide")

if "journal_memory" not in st.session_state:
    st.session_state.journal_memory = []

# Load model & prompt config
model_options = load_json_file("models.json", {
    "Gemini": ["gemini-3-flash-preview", "gemini-1.5-flash"],
    "ChatGPT": ["gpt-4o-mini", "gpt-4o"]
})

prompt_options = load_json_file(
    "prompts.json",
    {"Default": "Buat analisa Wyckoff dari {equity}."}
)

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("🎮 Control Panel")

    api_provider = st.selectbox(
        "Pilih API Provider:",
        ["Gemini", "ChatGPT"]
    )

    selected_model_name = st.selectbox(
        f"Pilih Model {api_provider}:",
        model_options[api_provider]
    )

    selected_prompt_key = st.selectbox(
        "Pilih Strategi Prompt:",
        list(prompt_options.keys())
    )

    st.divider()
    st.header("⚙️ Portofolio")
    equity = st.number_input("Total Modal (Rp)", value=9_500_000)

    st.divider()
    st.header("🔑 Konfigurasi API Key")

    if api_provider == "Gemini":
        api_key_input = st.text_input(
            "Gemini API Key:",
            value=st.secrets.get("GEMINI_API_KEY", ""),
            type="password"
        )
    else:
        api_key_input = st.text_input(
            "OpenAI API Key:",
            value=st.secrets.get("OPENAI_API_KEY", ""),
            type="password"
        )

    st.divider()
    if st.session_state.journal_memory:
        st.download_button(
            "📥 Download Jurnal (JSON)",
            json.dumps(st.session_state.journal_memory, indent=4),
            file_name=f"wyckoff_journal_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json"
        )

# --- 4. GEMINI ---
def generate_with_gemini(model_name, prompt, image=None, api_key=None):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)

        if image:
            response = model.generate_content([prompt, image])
        else:
            response = model.generate_content(prompt)

        return response.text, None
    except Exception as e:
        return None, str(e)

# --- 5. CHATGPT (OPENAI) ---
def generate_with_chatgpt(model_name, prompt, image=None, api_key=None):
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        content = [{"type": "text", "text": prompt}]

        if image:
            buf = BytesIO()
            image.save(buf, format="PNG")
            img_b64 = base64.b64encode(buf.getvalue()).decode()

            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_b64}"
                }
            })

        payload = {
            "model": model_name,
            "messages": [
                {"role": "user", "content": content}
            ],
            "temperature": 0.7
        }

        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )

        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"], None

        return None, r.text

    except Exception as e:
        return None, str(e)

# --- 6. MAIN ---
st.title("🧠 Wyckoff Brain – Modular")

uploaded_file = st.file_uploader(
    "Upload Screenshot Chart",
    type=["png", "jpg", "jpeg"]
)

if uploaded_file:
    img = Image.open(uploaded_file)
    st.image(img, use_container_width=True)

    if st.button("🚀 Jalankan Analisa"):
        api_key = api_key_input.strip()
        if not api_key:
            st.error("API Key wajib diisi")
            st.stop()

        last_analisa = (
            st.session_state.journal_memory[-1]["analysis"]
            if st.session_state.journal_memory else
            "Tidak ada analisa sebelumnya."
        )

        final_prompt = prompt_options[selected_prompt_key].format(
            equity=equity,
            last_analisa=last_analisa
        )

        with st.spinner("AI sedang menganalisa..."):
            if api_provider == "Gemini":
                result, error = generate_with_gemini(
                    selected_model_name,
                    final_prompt,
                    img,
                    api_key
                )
            else:
                result, error = generate_with_chatgpt(
                    selected_model_name,
                    final_prompt,
                    img,
                    api_key
                )

        if error:
            st.error(error)
        else:
            st.session_state.journal_memory.append({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "api": api_provider,
                "model": selected_model_name,
                "strategy": selected_prompt_key,
                "analysis": result
            })

            st.markdown("### 📊 Hasil Analisa")
            st.markdown(result)
            st.success("Analisa tersimpan!")

# --- 7. RIWAYAT ---
st.divider()
st.subheader("📜 Riwayat Analisa")

for m in reversed(st.session_state.journal_memory):
    with st.expander(
        f"{m['date']} | {m['api']} - {m['model']}"
    ):
        st.markdown(m["analysis"])
