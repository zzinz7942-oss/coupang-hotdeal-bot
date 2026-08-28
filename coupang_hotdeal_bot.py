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
        "GOOGLE_API_KEY": os.environ.get("GOOGLE_API_KEY", ""),
    }


def generate_ai_hook(google_api_key, prod_name, price):
    """Gemini로 짧은 후킹 문구 생성. 실패하면 고정 폴백 문구 사용."""
    fallback = "🔥 실시간 인기 폭발! 재고 소진 전 빠르게 득템하세요."
    if not google_api_key:
        return fallback
    prompt = (
        f"상품명: {prod_name}\n가격: {price:,}원\n\n"
        "위 상품을 사고 싶게 만드는 1문장짜리 후킹 카피를 작성해줘. "
        "이모지 1~2개 포함, URL/설명 없이 한 문장만 출력."
    )
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={google_api_key}"
        payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return fallback


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


def escape_html(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def build_caption(p, ai_hook):
    """상품 정보를 이모지/줄바꿈으로 가독성 좋게 구성한 HTML 캡션. URL은 본문에 넣지 않고 인라인 버튼으로 분리."""
    name = escape_html(p.get("productName", "상품"))
    price = p.get("productPrice", 0)
    category = p.get("categoryName", "")

    badges = []
    if p.get("isRocket"):
        badges.append("🚀로켓배송")
    if p.get("isFreeShipping"):
        badges.append("🆓무료배송")
    badge_line = " ".join(badges)

    lines = [f"🔥 <b>{name}</b>", ""]
    if category:
        cat_line = f"📂 {escape_html(category)}"
        if badge_line:
            cat_line += f" · {badge_line}"
        lines.append(cat_line)
    elif badge_line:
        lines.append(badge_line)

    lines.append(f"💰 <b>{price:,.0f}원</b> 특가")
    lines.append("")
    lines.append(escape_html(ai_hook))

    return "\n".join(lines)


def _inline_button(url):
    return json.dumps({"inline_keyboard": [[{"text": "🔥 쿠팡에서 바로 보러가기", "url": url}]]})


def send_telegram_photo(keys, photo_url, caption, product_url):
    """이미지(sendPhoto) + 인라인 버튼(URL 본문 미노출)으로 전송. 실패하면 예외를 던져 호출부에서 텍스트 폴백 처리."""
    token = keys["TELEGRAM_BOT_TOKEN"]
    chat_id = keys["TELEGRAM_CHAT_ID"]
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": _inline_button(product_url),
    }).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendPhoto", data=data)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def send_telegram_text(keys, text, product_url):
    """이미지가 없거나 sendPhoto가 실패했을 때의 텍스트+인라인 버튼 폴백"""
    token = keys["TELEGRAM_BOT_TOKEN"]
    chat_id = keys["TELEGRAM_CHAT_ID"]
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": _inline_button(product_url),
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
        # 상품 하나 처리 중 어떤 예외가 나도 전체 루프는 계속 진행 (다음 상품으로 넘어감)
        try:
            pid = str(p.get("productId"))
            if pid in sent_ids:
                continue

            name = p.get("productName", "상품")
            price = p.get("productPrice", 0)
            photo_url = p.get("productImage", "")
            product_url = p.get("productUrl", "")
            if not product_url:
                continue

            ai_hook = generate_ai_hook(keys.get("GOOGLE_API_KEY", ""), name, price)
            caption = build_caption(p, ai_hook)

            sent_ok = False
            if photo_url:
                try:
                    send_telegram_photo(keys, photo_url, caption, product_url)
                    sent_ok = True
                except Exception as e:
                    print(f"[경고] 이미지 전송 실패, 텍스트로 재시도 ({name}): {e}")

            if not sent_ok:
                try:
                    send_telegram_text(keys, caption, product_url)
                    sent_ok = True
                except Exception as e:
                    print(f"[에러] 텔레그램 전송 완전 실패 ({name}): {e}")

            if sent_ok:
                sent_ids.add(pid)
                new_count += 1
                time.sleep(1)
        except Exception as e:
            # 개별 상품 파싱/처리 단계에서의 예상 못한 오류도 흡수하고 다음 상품 진행
            print(f"[에러] 상품 처리 중 알 수 없는 오류 (건너뜀): {e}")
            continue

    save_sent(sent_ids)
    print(f"[완료] 신규 특가 {new_count}건 전송, 전체 확인 {len(products)}건")


if __name__ == "__main__":
    main()
