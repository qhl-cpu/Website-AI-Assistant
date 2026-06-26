import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

WP_BASE_URL = os.getenv("WP_BASE_URL")
WP_USERNAME = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")

response = requests.get(
    f"{WP_BASE_URL}/wp-json/wp/v2/pages",
    auth=HTTPBasicAuth(WP_USERNAME, WP_APP_PASSWORD),
    params={
        "status": "private",
        "per_page": 5,
    },
    timeout=20,
)

print("Status:", response.status_code)
print(response.text[:1000])