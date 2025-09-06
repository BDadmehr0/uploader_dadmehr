# secure_bot.py
import requests
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

# تنظیمات
API_TOKEN = "8005785657:AAHg3xlrCjQQz8hBSeXK-YXn94DzrmOwWac"  # توکن ربات مرکزی
SECRET_KEY = "supersecret"  # برای احراز هویت ربات‌های آپلودر

app = FastAPI()


class CheckUserRequest(BaseModel):
    user_id: int
    channels: list[str]  # لیست کانال‌ها از اپلودر


def is_user_member(user_id: int, channel_id: str):
    """بررسی عضویت کاربر در یک کانال خاص"""
    url = f"https://api.telegram.org/bot{API_TOKEN}/getChatMember"
    resp = requests.get(url, params={"chat_id": channel_id, "user_id": user_id}).json()
    status = resp.get("result", {}).get("status")
    member = status in ["member", "creator", "administrator"]
    print(resp)
    return member


@app.post("/check_user")
def check_user(req: CheckUserRequest, x_api_key: str = Header(...)):
    if x_api_key != SECRET_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")

    # بررسی عضویت کاربر در همه کانال‌های ارسال شده
    for channel in req.channels:
        if not is_user_member(req.user_id, channel):
            return {"status": "no"}  # اگر در یکی عضو نبود، خروجی "no"

    return {"status": "yes"}  # در همه کانال‌ها عضو است
