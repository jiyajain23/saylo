from google import genai

client = genai.Client()

print("--- Models supporting Gemini Live API ---")

# Pull all available models from AI Studio
for model in client.models.list():
    # The modern SDK uses model.supported_actions
    if model.supported_actions:
        # Check if the model supports live bidirectional audio/video actions
        is_live = any(
            "BidiGenerateContent" in action or "bidiGenerateContent" in action 
            # Normalise the casing just in case
            for action in model.supported_actions
        )
        
        if is_live:
            print(f"- {model.name}")
