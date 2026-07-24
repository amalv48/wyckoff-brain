import base64
import io
import os


def _image_to_b64_png(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("utf-8")


def _to_gemini_schema(schema):
    """The installed google-generativeai SDK (0.8.x) doesn't understand the
    standard JSON Schema `"type": ["number", "null"]` union form used for
    nullable fields — it wants `"type": "number", "nullable": true` instead.
    Recursively rewrite a schema written in the standard form into that
    dialect so one canonical schema can drive both providers."""
    if isinstance(schema, dict):
        out = {k: _to_gemini_schema(v) for k, v in schema.items() if k != "additionalProperties"}
        type_val = schema.get("type")
        if isinstance(type_val, list):
            non_null = [t for t in type_val if t != "null"]
            out["type"] = non_null[0] if len(non_null) == 1 else non_null
            if "null" in type_val:
                out["nullable"] = True
        return out
    if isinstance(schema, list):
        return [_to_gemini_schema(v) for v in schema]
    return schema


def call_gemini(model_id, prompt, image=None, response_schema=None):
    import google.generativeai as genai

    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    generation_config = None
    if response_schema is not None:
        generation_config = genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=_to_gemini_schema(response_schema),
        )
    model = genai.GenerativeModel(model_id, generation_config=generation_config)
    content = [prompt, image] if image is not None else [prompt]
    response = model.generate_content(content)
    return response.text


def call_claude(model_id, prompt, image=None, response_schema=None):
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
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

    kwargs = {}
    if response_schema is not None:
        kwargs["output_config"] = {"format": {"type": "json_schema", "schema": response_schema}}

    response = client.messages.create(
        model=model_id,
        max_tokens=4096,
        messages=[{"role": "user", "content": user_content}],
        **kwargs,
    )
    return "".join(block.text for block in response.content if block.type == "text")


def call_model(provider, model_id, prompt, image=None, response_schema=None):
    if provider == "Claude":
        return call_claude(model_id, prompt, image=image, response_schema=response_schema)
    if provider == "Gemini":
        return call_gemini(model_id, prompt, image=image, response_schema=response_schema)
    raise ValueError(f"Unknown provider: {provider}")
