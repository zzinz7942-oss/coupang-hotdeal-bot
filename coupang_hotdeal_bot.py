"""
쿠팡파트너스 골드박스(특가) -> 텔레그램 자동 알림 (GitHub Actions용)
- 환경변수로 키를 받음: COUPANG_ACCESS_KEY, COUPANG_SECRET_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
- 이미 보낸 상품은 sent_products.json에 기록해 중복 전송 방지 (저장소에 커밋되어 유지됨)
"""

import hashlib
import hmac
import json
import os
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SENT_FILE = os.path.join(BASE_DIR, "sent_products.json")

DOMAIN = "https://api-gateway.coupang.com"
GOLDBOX_PATH = "/v2/providers/affiliate_open_api/apis/openapi/v1/products/bestcategories/1001"


def load_keys():
    return {
        "COUPANG_ACCESS_KEY": os.environ["COUPANG_ACCESS_KEY"],
        "COUPANG_SECRET_KEY": os.environ["COUPANG_SECRET_KEY"],
        "TELEGRAM_BOT_TOKEN": os.environ["TELEGRAM_BOT_TOKEN"],
        "TELEGRAM_CHAT_ID": os.environ["TELEGRAM_CHAT_ID"],
    }


def load_sent():
    if os.path.exists(SENT_FILE):
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_sent(sent_ids):
    with open(SENT_FILE, "w", encoding="utf-8") as f:
        json.dump(list(sent_ids), f)


def generate_hmac(method, url_path_with_query, access_key, secret_key):
    datetime_gmt = datetime.now(timezone.utc).strftime("%y%m%d") + "T" + datetime.now(timezone.utc).strftime("%H%M%S") + "Z"
    message = datetime_gmt + method + url_path_with_query
    signature = hmac.new(
        bytes(secret_key, "utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={datetime_gmt}, signature={signature}"


def fetch_goldbox(keys):
    method = "GET"
    query = urllib.parse.urlencode({"limit": 20})
    auth_header = generate_hmac(method, GOLDBOX_PATH + query, keys["COUPANG_ACCESS_KEY"], keys["COUPANG_SECRET_KEY"])

    path_with_query = f"{GOLDBOX_PATH}?{query}"
    req = urllib.request.Request(
        DOMAIN + path_with_query,
        headers={
            "Authorization": auth_header,
            "Content-Type": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(f"[디버그] HTTP {e.code} 응답 본문: {body}")
        raise


def send_telegram(keys, text):
    token = keys["TELEGRAM_BOT_TOKEN"]
    chat_id = keys["TELEGRAM_CHAT_ID"]
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "false"
    }).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    keys = load_keys()
    sent_ids = load_sent()

    try:
        result = fetch_goldbox(keys)
    except Exception as e:
        print(f"[에러] 쿠팡 API 호출 실패: {e}")
        return

    data = result.get("data", [])
    products = data if isinstance(data, list) else data.get("productData", [])
    if not products:
        print("[정보] 조회된 상품이 없습니다.")
        print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])
        return

    new_count = 0
    for p in products:
        pid = str(p.get("productId"))
        if pid in sent_ids:
            continue

        name = p.get("productName", "상품")
        price = p.get("productPrice", 0)
        url = p.get("productUrl", "")

        msg = f"🔥 <b>{name}</b>\n가격: {price:,}원\n{url}"
        try:
            send_telegram(keys, msg)
            sent_ids.add(pid)
            new_count += 1
            time.sleep(1)
        except Exception as e:
            print(f"[에러] 텔레그램 전송 실패 ({name}): {e}")

    save_sent(sent_ids)
    print(f"[완료] 신규 특가 {new_count}건 전송, 전체 확인 {len(products)}건")


if __name__ == "__main__":
    main()
