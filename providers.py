import base64
import io

import streamlit as st


def _image_to_b64_png(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("utf-8")


def call_gemini(model_id, prompt, image=None):
    import google.generativeai as genai

    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel(model_id)
    content = [prompt, image] if image is not None else [prompt]
    response = model.generate_content(content)
    return response.text


def call_claude(model_id, prompt, image=None):
    import anthropic

    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    user_content = []
    if image is not None:
        user_content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": _image_to_b64_png(image),
            },
        })
    user_content.append({"type": "text", "text": prompt})

    response = client.messages.create(
        model=model_id,
        max_tokens=4096,
        messages=[{"role": "user", "content": user_content}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def call_model(provider, model_id, prompt, image=None):
    if provider == "Claude":
        return call_claude(model_id, prompt, image=image)
    if provider == "Gemini":
        return call_gemini(model_id, prompt, image=image)
    raise ValueError(f"Unknown provider: {provider}")
