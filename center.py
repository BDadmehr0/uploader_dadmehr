# secure_bot.py
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
import requests
import redis

# تنظیمات
API_TOKEN = "8005785657:AAHg3xlrCjQQz8hBSeXK-YXn94DzrmOwWac"  # توکن ربات مرکزی https://t.me/center_testasdasdasd_bot
CHANNEL_ID = "@faststrongch"
SECRET_KEY = "supersecret"  # برای احراز هویت ربات‌های آپلودر
REDIS_URL = "redis://localhost:6379"
r = redis.from_url(REDIS_URL, decode_responses=True)

app = FastAPI()

class CheckUserRequest(BaseModel):
    user_id: int

def is_user_member(user_id: int):
    # چک کش اول
    cached = r.get(f"membership:{user_id}")
    if cached:
        return cached == "yes"

    # تماس با تلگرام
    url = f"https://api.telegram.org/bot{API_TOKEN}/getChatMember"
    resp = requests.get(url, params={"chat_id": CHANNEL_ID, "user_id": user_id}).json()
    print(resp)

    
    status = resp.get("result", {}).get("status")
    member = status in ["member", "creator", "administrator"]
    
    # کش کردن نتیجه 5 دقیقه
    r.setex(f"membership:{user_id}", 300, "yes" if member else "no")
    
    return member

@app.post("/check_user")
def check_user(req: CheckUserRequest, x_api_key: str = Header(...)):
    if x_api_key != SECRET_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    member = is_user_member(req.user_id)
    return {"status": "yes" if member else "no"}
