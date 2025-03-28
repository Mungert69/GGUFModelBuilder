import requests
import gradio as gr
import io
from PIL import Image
import os
from datetime import datetime
import re
import time
import gc  # Import garbage collection module
from dotenv import load_dotenv

# Load the .env file
load_dotenv()

# Read the API token from the .env file
api_token = os.getenv("HF_API_TOKEN")

# Hugging Face API settings
API_URL = "https://api-inference.huggingface.co/models/sd-community/sdxl-flash"

# Function to query the API with retry mechanism and 30-second wait between retries
def query(payload, timeout=300, retries=5, delay=30):
    headers = {  # Reinitialize headers on each call
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "x-wait-for-model": "true"
    }
    for attempt in range(retries):
        response = requests.post(API_URL, headers=headers, json=payload, timeout=timeout)
        
        if response.status_code == 200:
            return response.content
        elif response.status_code == 503:
            print("Model is still loading, waiting 30 seconds before retrying...")
        elif response.status_code == 429:
            print("Rate limit hit, waiting 30 seconds before retrying...")
        else:
            raise Exception(f"Failed to generate image. Status code: {response.status_code}, Response: {response.text}")
        
        time.sleep(delay)  # Wait before retrying
    
    raise Exception("Failed to generate image after multiple attempts due to model loading or rate limit.")

# Function to clean prompt text for a safe filename
def sanitize_filename(prompt):
    sanitized = re.sub(r'[^a-zA-Z0-9\s]', '', prompt)
    sanitized = "_".join(sanitized.split()).strip()[:50]  # Limit to 50 characters
    return sanitized

# Function to generate image from prompt and save it locally
def generate_image(prompt):
    # Send prompt to Hugging Face API
    payload = {"inputs": prompt}
    image_bytes = query(payload)
    
    # Convert image bytes to PIL Image
    image = Image.open(io.BytesIO(image_bytes))
    
    # Generate a filename from the sanitized prompt and timestamp
    prompt_part = sanitize_filename(prompt)
    filename = f"{prompt_part}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    save_path = os.path.join("generated_images", filename)
    os.makedirs("generated_images", exist_ok=True)  # Ensure directory exists
    
    # Save the image locally
    image.save(save_path)
    print(f"Image saved at: {save_path}")
    
    # Close the image and force garbage collection
    image.close()
    gc.collect()  # Explicitly run garbage collection
    
    return Image.open(save_path)  # Return a new Image object for Gradio

# Gradio Interface with queue and max_size configuration for handling longer requests
iface = gr.Interface(
    fn=generate_image,
    inputs="text",
    outputs="image",
    title="Image Generation with LLM",
    description="Enter a prompt to generate an image using an LLM model.",
    live=False  # Prevents UI from updating until function completes
).queue(
    max_size=10  # Max number of requests in the queue
)

# Launch the Gradio app
iface.launch()

