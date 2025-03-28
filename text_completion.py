import gradio as gr
from huggingface_hub import InferenceClient
from dotenv import load_dotenv

# Load the .env file
load_dotenv()

# Read the API token from the .env file
api_token = os.getenv("HF_API_TOKEN")
# Initialize the Hugging Face Inference Client
client = InferenceClient(api_key=api_token)

# Function to interact with the model and stream response in Markdown
def chat_with_model(user_message):
    # Token limit set to ensure the combined input and output fit within 32768 tokens
    input_token_count = len(user_message.split())  # Rough estimation for simplicity
    max_tokens = min(32768 - input_token_count, 1000)  # Adjusts max_tokens based on input length
    
    messages = [
        {"role": "user", "content": user_message}
    ]

    # Start streaming the response from the model
    stream = client.chat.completions.create(
        model="mistralai/Mistral-Nemo-Instruct-2407",
        messages=messages,
        max_tokens=max_tokens,
        stream=True
    )

    response_text = ""
    # Collect the chunks of response to display in real-time
    for chunk in stream:
        chunk_content = chunk.choices[0].delta.content
        response_text += chunk_content
        yield response_text  # Yield the response incrementally for real-time display

# Gradio interface setup with Markdown output
iface = gr.Interface(
    fn=chat_with_model,
    inputs="text",
    outputs=gr.Markdown(),  # Use Markdown to render model's output with proper formatting
    title="Chat with Mistral-Nemo-Instruct",
    description="Enter a question or prompt and see the response in real-time."
)

# Launch the Gradio app
iface.launch()

