"""
쿠팡 골드박스 특가 -> 세로 숏폼(쇼츠) 영상 자동 생성
- 상품 이미지를 다운받아 켄번즈(zoompan) 효과 + 가격/이름 자막을 입힌 mp4 생성
- 출력: shorts_output/short_<productId>.mp4 (1080x1920, 5초)
"""

import hashlib
import hmac
import json
import os
import subprocess
import urllib.request
import urllib.parse
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "shorts_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

DOMAIN = "https://api-gateway.coupang.com"
GOLDBOX_PATH = "/v2/providers/affiliate_open_api/apis/openapi/v1/products/bestcategories/1001"


def load_keys():
    keys_env = {k: os.environ.get(k) for k in
                ["COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY"]}
    if all(keys_env.values()):
        return keys_env
    keys_file = r"G:\내 드라이브\AI_JARVIS\AI_JARVIS_AGENT\keys.json"
    with open(keys_file, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_hmac(method, url_path_with_query, access_key, secret_key):
    dt = datetime.now(timezone.utc).strftime("%y%m%d") + "T" + datetime.now(timezone.utc).strftime("%H%M%S") + "Z"
    message = dt + method + url_path_with_query
    signature = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={dt}, signature={signature}"


def fetch_goldbox(keys, limit=5):
    method = "GET"
    query = urllib.parse.urlencode({"limit": limit})
    auth = generate_hmac(method, GOLDBOX_PATH + query, keys["COUPANG_ACCESS_KEY"], keys["COUPANG_SECRET_KEY"])
    req = urllib.request.Request(DOMAIN + GOLDBOX_PATH + "?" + query, headers={"Authorization": auth})
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    data = result.get("data", [])
    return data if isinstance(data, list) else data.get("productData", [])


def download_image(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp, open(dest, "wb") as f:
        f.write(resp.read())


def escape_ass_text(text):
    return text.replace("\\", "\\\\").replace("{", "").replace("}", "").replace("\n", "\\N")


def write_ass_subtitle(path, product_name, price):
    name_line = escape_ass_text(product_name[:40])
    price_line = f"{price:,.0f}원 특가"
    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Name,Malgun Gothic,54,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,4,2,2,60,60,220,1
Style: Price,Malgun Gothic,90,&H0000A5FF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,3,2,60,60,90,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:05.00,Name,,0,0,0,,{name_line}
Dialogue: 0,0:00:00.00,0:00:05.00,Price,,0,0,0,,{price_line}
"""
    with open(path, "w", encoding="utf-8-sig") as f:
        f.write(ass_content)


def make_short(image_path, ass_path, output_path, duration=5):
    ass_path_ffmpeg = ass_path.replace("\\", "/").replace(":", "\\:")
    filter_complex = (
        f"scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,"
        f"zoompan=z='min(zoom+0.0008,1.15)':d={duration*25}:s=1080x1920:fps=25,"
        f"subtitles='{ass_path_ffmpeg}'"
    )
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,
        "-t", str(duration),
        "-vf", filter_complex,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        output_path
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")


def main():
    keys = load_keys()
    products = fetch_goldbox(keys, limit=5)

    if not products:
        print("[정보] 조회된 상품이 없습니다.")
        return

    for p in products:
        pid = str(p.get("productId"))
        name = p.get("productName", "특가상품")
        price = p.get("productPrice", 0)
        image_url = p.get("productImage", "")

        if not image_url:
            continue

        img_path = os.path.join(OUTPUT_DIR, f"tmp_{pid}.jpg")
        ass_path = os.path.join(OUTPUT_DIR, f"tmp_{pid}.ass")
        out_path = os.path.join(OUTPUT_DIR, f"short_{pid}.mp4")

        try:
            download_image(image_url, img_path)
            write_ass_subtitle(ass_path, name, price)
            make_short(img_path, ass_path, out_path)
            print(f"[완료] {out_path}")
        except subprocess.CalledProcessError as e:
            print(f"[에러] ffmpeg 실패 ({name}): {e.stderr[-500:]}")
        except Exception as e:
            print(f"[에러] 처리 실패 ({name}): {e}")
        finally:
            for tmp in (img_path, ass_path):
                if os.path.exists(tmp):
                    os.remove(tmp)


if __name__ == "__main__":
    main()
