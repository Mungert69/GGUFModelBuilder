from huggingface_hub import InferenceClient
import gradio as gr
from dotenv import load_dotenv

# Load the .env file
load_dotenv()

# Read the API token from the .env file
api_token = os.getenv("HF_API_TOKEN")

# Initialize the Hugging Face Inference Client
client = InferenceClient(api_key=api_token)

# Function to send the image URL and prompt to the model and stream the response
def describe_image(image_url, prompt):
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": prompt},
            ],
        }
    ]

    # Stream the response from the model
    response_text = ""
    for message in client.chat_completion(
        model="meta-llama/Llama-3.2-11B-Vision-Instruct",
        messages=messages,
        max_tokens=500,
        stream=True
    ):
        chunk_content = message.choices[0].delta.content
        response_text += chunk_content
        yield response_text  # Yield each chunk to display incrementally

# Gradio interface setup for image URL input and Markdown output
iface = gr.Interface(
    fn=describe_image,
    inputs=[
        gr.Textbox(label="Image URL", placeholder="Enter image URL"),
        gr.Textbox(label="Prompt", placeholder="Enter a description prompt, e.g., 'Describe this image in one sentence.'"),
    ],
    outputs=gr.Markdown(),  # Use Markdown to render response
    title="Image Description with Vision-Enhanced Model",
    description="Provide an image URL and a prompt. The model will describe the image based on your prompt."
)

# Launch the Gradio app
iface.launch()

