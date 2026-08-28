"""
쿠팡 골드박스 특가 -> 쇼츠(mp4) 생성 -> 텔레그램 채널에 sendVideo로 전송
- generate_shorts_v2.py의 검증된 함수(fetch_goldbox, download_image, write_ass_subtitle, make_short)를 재사용
- 중복 방지: shorts_sent.json
"""

import json
import os
import time
import urllib.request
import urllib.parse

import generate_shorts_v2 as shorts

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SENT_FILE = os.path.join(BASE_DIR, "shorts_sent.json")


def load_sent():
    if os.path.exists(SENT_FILE):
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_sent(sent_ids):
    with open(SENT_FILE, "w", encoding="utf-8") as f:
        json.dump(list(sent_ids), f)


def send_telegram_video(token, chat_id, video_path, caption=""):
    url = f"https://api.telegram.org/bot{token}/sendVideo"
    boundary = "----ShortsUploadBoundary"
    with open(video_path, "rb") as f:
        video_bytes = f.read()

    body = b""
    for field, value in [("chat_id", chat_id), ("caption", caption)]:
        body += (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"\r\n\r\n{value}\r\n"
        ).encode("utf-8")
    body += (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"video\"; filename=\"short.mp4\"\r\n"
        f"Content-Type: video/mp4\r\n\r\n"
    ).encode("utf-8")
    body += video_bytes
    body += f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    keys = shorts.load_keys()
    with open(r"G:\내 드라이브\AI_JARVIS\AI_JARVIS_AGENT\keys.json", "r", encoding="utf-8") as f:
        full_keys = json.load(f)

    token = full_keys["HOTDEAL_TELEGRAM_BOT_TOKEN"]
    chat_id = full_keys["HOTDEAL_TELEGRAM_CHAT_ID"]

    sent_ids = load_sent()
    products = shorts.fetch_goldbox(keys, limit=5)

    if not products:
        print("[정보] 조회된 상품이 없습니다.")
        return

    sent_count = 0
    for p in products:
        pid = str(p.get("productId"))
        if pid in sent_ids:
            continue

        name = p.get("productName", "특가상품")
        price = p.get("productPrice", 0)
        image_url = p.get("productImage", "")
        product_url = p.get("productUrl", "")

        if not image_url:
            continue

        img_path = os.path.join(shorts.OUTPUT_DIR, f"tmp_{pid}.jpg")
        ass_path = os.path.join(shorts.OUTPUT_DIR, f"tmp_{pid}.ass")
        out_path = os.path.join(shorts.OUTPUT_DIR, f"short_{pid}.mp4")

        try:
            shorts.download_image(image_url, img_path)
            shorts.write_ass_subtitle(ass_path, name, price, product_id=pid)
            shorts.make_short(img_path, ass_path, out_path)

            caption = f"{name}\n{price:,.0f}원\n{product_url}"[:1024]
            send_telegram_video(token, chat_id, out_path, caption)

            sent_ids.add(pid)
            sent_count += 1
            print(f"[완료] {name} 전송 성공")
            time.sleep(2)
        except Exception as e:
            print(f"[에러] {name} 처리 실패: {e}")
        finally:
            for tmp in (img_path, ass_path, out_path):
                if os.path.exists(tmp):
                    os.remove(tmp)

    save_sent(sent_ids)
    print(f"[전체 완료] 신규 쇼츠 {sent_count}건 전송")


if __name__ == "__main__":
    main()
