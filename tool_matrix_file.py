import os
from transformers import AutoTokenizer
import pandas as pd

# Resolve the model path
model_path = os.path.expanduser("~/.cache/huggingface/hub/models--google--gemma-3-1b-it/snapshots/9b99be88fdd7a2496bf644baade44348ad736c95")

# Load the tokenizer
tokenizer = AutoTokenizer.from_pretrained(model_path)

# Load the .parquet file
df = pd.read_parquet("function-think.parquet")

# Inspect the .parquet file
print("Columns in the .parquet file:", df.columns.tolist())
print("First few rows of the .parquet file:")
print(df.head())

# Define role mapping
role_mapping = {
    "human": "user",
    "model": "assistant"
}

# Convert the data into the format expected by the chat template
formatted_data = []
for _, row in df.iterrows():
    # Extract the list of conversations
    conversations = row["conversations"]
    
    # Update roles using the mapping
    updated_conversations = []
    for conversation in conversations:
        updated_conversation = {
            "role": role_mapping.get(conversation["role"]),  # Map the role
            "content": conversation["content"]  # Keep the content unchanged
        }
        updated_conversations.append(updated_conversation)

    # Format the conversations using the chat template
    formatted_example = tokenizer.apply_chat_template(
        updated_conversations,  # Pass the entire conversation
        tokenize=False,  # Don't tokenize, just format
        add_generation_prompt=True  # Add generation prompt if needed
    )
    formatted_data.append(formatted_example)

# Save to a text file
with open("formatted_data.txt", "w") as f:
    for example in formatted_data:
        f.write(example + "\n")
