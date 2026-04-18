import pandas as pd

df = pd.read_excel("sample_data.xlsx")
print(df.head())
print("\nColumns:", list(df.columns))
print("Shape:", df.shape)