import pandas as pd

# Load the .parquet file
df = pd.read_parquet("function-think.parquet")

# Print the column names
print("Columns in the .parquet file:", df.columns.tolist())

# Print the first few rows
print("First few rows of the .parquet file:")
print(df.head())
