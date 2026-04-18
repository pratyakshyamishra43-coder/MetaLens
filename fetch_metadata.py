import requests

token = "eyJraWQiOiJHYjM4OWEtOWY3Ni1nZGpzLWE5MmotMDI0MmJrOTQzNTYiLCJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJvcGVuLW1ldGFkYXRhLm9yZyIsInN1YiI6InByYXR5YWtzaHlhLjEyMTY4MSIsInJvbGVzIjpbXSwiZW1haWwiOiJwcmF0eWFrc2h5YS4xMjE2ODFAZ21haWwuY29tIiwiaXNCb3QiOmZhbHNlLCJ0b2tlblR5cGUiOiJQRVJTT05BTF9BQ0NFU1MiLCJ1c2VybmFtZSI6InByYXR5YWtzaHlhLjEyMTY4MSIsInByZWZlcnJlZF91c2VybmFtZSI6InByYXR5YWtzaHlhLjEyMTY4MSIsImlhdCI6MTc3NjUwOTYzNywiZXhwIjoxNzg0Mjg1NjM3fQ.bZTPAbrviwl6lO3PZvggkDWRZC2jvcrBh0KhBtr9IlIcL-Vrnk2NKntDpfKQ138-Nwetksg1wK5NVhsICcar_nylRs9_nn-0CBor0hdfgPGYNkZv_oDJ1pc1enBbLuPkXkKnta4BYRjLUv7Ei-OpkfXxQ5f20QE_72NUGB9lQpvacBvTqMLJ-r1YktpL47BZB1beO740NUsEmvRIfBE4W7KXI2uOC_nSidRHgQXxCzkJXC6xOo4oFlDiZq1b3WQYr_c3hknNpcBCB9v8vSvDR1uXDJd-tF_o6zwItzzBJz_-fEWCs_kkjizYUTV662_cibhAcPvVapLdAZFR1Vn17g"
headers = {"Authorization": f"Bearer {token}"}

FQN = "ACME_MYSQL.default.FINANCIAL_STAGING.ACCOUNTS"

response = requests.get(
    f"https://sandbox.open-metadata.org/api/v1/tables/name/{FQN}?fields=columns,tags,owners",
    headers=headers
)

data = response.json()

print("Table:", data["name"])
print("FQN:", data["fullyQualifiedName"])
print("Description:", data.get("description", "None"))
print("\nColumns:")
for col in data["columns"]:
    tags = [t["tagFQN"] for t in col.get("tags", [])]
    print(f"  - {col['name']} ({col['dataType']}) | Tags: {tags}")