import os
from update_readme import update_readme  # Import your update_readme function

# Test parameters
test_model_dir = "test_model"  # This is the folder where README.md will reside
test_base_name = "Test-1B-Instruct"  # Use the model name or any test name

# Create test folder and README.md for testing purposes
os.makedirs(test_model_dir, exist_ok=True)

# Sample content for the initial README.md
initial_readme_content = """
---

## Metadata
Some metadata info goes here.

---

Rest of the TEXT from the model here 
"""

# Write the initial README.md content to the test file
readme_file = os.path.join(test_model_dir, "README.md")
with open(readme_file, "w") as file:
    file.write(initial_readme_content)

# Now, call the update_readme function to update the README.md with the new section
try:
    update_readme(test_model_dir, test_base_name)
    print("README.md has been successfully updated.")
except FileNotFoundError as e:
    print(f"Error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")

# Optionally, read and print the updated README.md to verify the changes
with open(readme_file, "r") as file:
    updated_content = file.read()
    print("\nUpdated README.md Content:")
    print(updated_content)

