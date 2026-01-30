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
if "selected_api" not in st.session_state:
    st.session_state.selected_api = "Gemini"  # Default

# Load data model dan prompt
model_options = load_json_file("models.json", {
    "Gemini": ["gemini-3-flash-preview", "gemini-1.5-flash"],
    "Deepseek": ["deepseek-chat"]
})
prompt_options = load_json_file("prompts.json", {"Default": "Buat analisa Wyckoff dari {equity}."})

# --- 3. SIDEBAR (KONTROL MODULAR) ---
with st.sidebar:
    st.header("🎮 Control Panel")
    
    # Dropdown Pilih API Provider
    api_provider = st.selectbox(
        "Pilih API Provider:",
        ["Gemini", "Deepseek"],
        key="api_provider",
        help="Pilih penyedia layanan AI yang akan digunakan"
    )
    
    # Dropdown Pilih Model berdasarkan API yang dipilih
    if api_provider in model_options:
        selected_model_name = st.selectbox(
            f"Pilih Model {api_provider}:",
            model_options[api_provider],
            key="model_selection"
        )
    else:
        selected_model_name = st.selectbox(
            "Pilih Model:",
            model_options.get("Gemini", ["gemini-3-flash-preview"]),
            key="model_selection"
        )
    
    # Dropdown Pilih Prompt
    selected_prompt_key = st.selectbox("Pilih Strategi Prompt:", list(prompt_options.keys()))
    
    st.divider()
    st.header("⚙️ Portofolio")
    equity = st.number_input("Total Modal (Rp)", value=9500000)
    
    # Tampilkan API Key input berdasarkan provider
    st.divider()
    st.header("🔑 Konfigurasi API Key")
    
    if api_provider == "Gemini":
        api_key_input = st.text_input(
            "Gemini API Key:",
            value=st.secrets.get("GEMINI_API_KEY", "") if "GEMINI_API_KEY" in st.secrets else "",
            type="password",
            help="Dapatkan API Key dari https://makersuite.google.com/app/apikey"
        )
    else:  # Deepseek
        api_key_input = st.text_input(
            "Deepseek API Key:",
            value=st.secrets.get("DEEPSEEK_API_KEY", "") if "DEEPSEEK_API_KEY" in st.secrets else "",
            type="password",
            help="Dapatkan API Key dari https://platform.deepseek.com/api_keys"
        )
    
    st.divider()
    if st.session_state.journal_memory:
        json_data = json.dumps(st.session_state.journal_memory, indent=4)
        st.download_button(
            label="📥 Download Jurnal (JSON)",
            data=json_data,
            file_name=f"wyckoff_journal_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json"
        )

# --- 4. FUNGSI GENERATE RESPONSE BERDASARKAN API PROVIDER ---
def generate_with_gemini(model_name, prompt, image=None, api_key=None):
    """Generate response menggunakan Gemini API"""
    try:
        genai.configure(api_key=api_key or st.secrets.get("GEMINI_API_KEY", ""))
        model = genai.GenerativeModel(model_name)
        
        if image:
            response = model.generate_content([prompt, image])
        else:
            response = model.generate_content(prompt)
        
        return response.text, None
    except Exception as e:
        return None, f"Gemini API Error: {str(e)}"

def generate_with_deepseek(model_name, prompt, image=None, api_key=None):
    """Generate response menggunakan Deepseek API"""
    try:
        api_key = api_key or st.secrets.get("DEEPSEEK_API_KEY", "")
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Format payload berdasarkan apakah ada gambar atau tidak
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt}
                    ]
                }
            ],
            "stream": False
        }
        
        # Jika ada gambar, tambahkan sebagai base64
        if image:
            # Konversi PIL Image ke base64
            buffered = BytesIO()
            image.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            
            payload["messages"][0]["content"].append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_str}"
                }
            })
        
        # Kirim request ke API Deepseek
        response = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"], None
        else:
            return None, f"Deepseek API Error {response.status_code}: {response.text}"
            
    except Exception as e:
        return None, f"Deepseek Error: {str(e)}"

# --- 5. MAIN INTERFACE ---
st.title("🧠 Wyckoff Brain: Modular Version")
st.info(f"**API Aktif:** {api_provider} | **Model:** {selected_model_name} | **Strategi:** {selected_prompt_key}")

uploaded_file = st.file_uploader("Upload Screenshot Chart", type=["png", "jpg", "jpeg"])

if uploaded_file:
    img = Image.open(uploaded_file)
    st.image(img, caption="Chart Saham", use_container_width=True)

    if st.button("🚀 Jalankan Analisa"):
        # Validasi API Key
        if api_provider == "Gemini":
            api_key = api_key_input if api_key_input else st.secrets.get("GEMINI_API_KEY", "")
            if not api_key:
                st.error("⚠️ Masukkan Gemini API Key terlebih dahulu!")
                st.stop()
        else:  # Deepseek
            api_key = api_key_input if api_key_input else st.secrets.get("DEEPSEEK_API_KEY", "")
            if not api_key:
                st.error("⚠️ Masukkan Deepseek API Key terlebih dahulu!")
                st.stop()
        
        last_analisa = st.session_state.journal_memory[-1]['analysis'] if st.session_state.journal_memory else "Tidak ada data sebelumnya."
        
        # Ambil template prompt dan suntikkan variabel
        raw_prompt = prompt_options[selected_prompt_key]
        final_prompt = raw_prompt.format(last_analisa=last_analisa, equity=equity)

        with st.spinner(f"Otak ({api_provider} - {selected_model_name}) sedang berpikir..."):
            try:
                # Pilih fungsi generate berdasarkan provider
                if api_provider == "Gemini":
                    output_text, error = generate_with_gemini(
                        selected_model_name, 
                        final_prompt, 
                        img, 
                        api_key
                    )
                else:  # Deepseek
                    output_text, error = generate_with_deepseek(
                        selected_model_name, 
                        final_prompt, 
                        img, 
                        api_key
                    )
                
                if error:
                    st.error(f"Analisa Gagal: {error}")
                else:
                    # Simpan ke Memori
                    st.session_state.journal_memory.append({
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "api": api_provider,
                        "model": selected_model_name,
                        "strategy": selected_prompt_key,
                        "analysis": output_text
                    })
                    
                    st.markdown(f"### 📊 Hasil Analisa: {selected_prompt_key}")
                    st.markdown(output_text)
                    st.success("Analisa tersimpan dalam sesi ini!")
                
            except Exception as e:
                st.error(f"Analisa Gagal: {e}")

# --- 6. RIWAYAT ---
st.divider()
st.subheader("📜 Riwayat Analisa")
if st.session_state.journal_memory:
    for m in reversed(st.session_state.journal_memory):
        with st.expander(f"{m['date']} | {m['api']} - {m['strategy']} ({m['model']})"):
            st.markdown(m['analysis'])
