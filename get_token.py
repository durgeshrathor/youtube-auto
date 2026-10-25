# Sirf EK BAAR apne computer par chalao: python get_token.py
# client_secret.json ho to wo use hoti hai, nahi ho to Client ID / Secret poochta hai.
import json, os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

if os.path.exists("client_secret.json"):
    cfg = json.load(open("client_secret.json"))
    cfg = cfg.get("installed") or cfg.get("web")
    client_id, client_secret = cfg["client_id"], cfg["client_secret"]
else:
    client_id = input("Client ID paste karo: ").strip()
    client_secret = input("Client secret paste karo: ").strip()

config = {"installed": {
    "client_id": client_id,
    "client_secret": client_secret,
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "redirect_uris": ["http://localhost"],
}}
flow = InstalledAppFlow.from_client_config(config, SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

print("\n===== Ye 3 values GitHub Secrets me daalo =====")
print("YT_CLIENT_ID     =", client_id)
print("YT_CLIENT_SECRET =", client_secret)
print("YT_REFRESH_TOKEN =", creds.refresh_token)
