"""
쿠팡 골드박스 특가 -> 세로 숏폼(쇼츠) 영상 자동 생성 (v2)
- 착용/휴대 가능한 상품(시계, 양말, 신발, 안경 등): ComfyUI IP-Adapter로 모델 착용샷 생성 후 영상화
- 그 외 상품(소모품, 세척용품 등): 기존 제품샷 켄번즈 방식
- 출력: shorts_output/short_<productId>.mp4
"""

import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from category_router import should_use_realistic

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "shorts_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

DOMAIN = "https://api-gateway.coupang.com"
GOLDBOX_PATH = "/v2/providers/affiliate_open_api/apis/openapi/v1/products/bestcategories/1001"

COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")


def load_keys():
    keys_env = {k: os.environ.get(k) for k in ["COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY"]}
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


def upload_to_comfyui(image_path):
    """상품 이미지를 ComfyUI input 디렉토리에 업로드"""
    with open(image_path, "rb") as f:
        img_data = f.read()

    boundary = "----ShortsFormBoundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="ref.jpg"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode() + img_data + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{COMFYUI_URL}/upload/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode())
    return result["name"]


def generate_realistic_model_image(ref_filename, product_name, out_path):
    """IP-Adapter 워크플로우로 모델 착용샷 생성"""
    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "juggernautXL.safetensors"}},
        "2": {"class_type": "LoadImage", "inputs": {"image": ref_filename}},
        "3": {"class_type": "IPAdapterUnifiedLoader", "inputs": {"model": ["1", 0], "preset": "STANDARD (medium strength)"}},
        "4": {"class_type": "IPAdapter", "inputs": {
            "model": ["3", 0], "ipadapter": ["3", 1], "image": ["2", 0],
            "weight": 0.8, "weight_type": "standard", "combine_embeds": "concat",
            "start_at": 0.0, "end_at": 1.0, "embeds_scaling": "V only"
        }},
        "5": {"class_type": "CLIPTextEncode", "inputs": {
            "clip": ["1", 1],
            "text": (
                f"korean model happily wearing/using {product_name}, "
                "confident satisfied smiling expression, dynamic lifestyle advertisement pose, "
                "commercial product advertisement photography, bright vibrant studio lighting, "
                "shallow depth of field, glossy premium look, eye-catching composition, "
                "photorealistic, 8k, professional ad campaign shot"
            )
        }},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": "blurry, low quality, deformed, watermark, text, dull, sad expression, boring pose, flat lighting"}},
        "7": {"class_type": "EmptyLatentImage", "inputs": {"width": 1080, "height": 1920, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {
            "model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["7", 0],
            "seed": int(time.time()), "steps": 30, "cfg": 6.5, "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 1.0
        }},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["1", 2]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "shorts_realistic"}},
    }

    req = urllib.request.Request(
        f"{COMFYUI_URL}/prompt",
        data=json.dumps({"prompt": workflow}).encode(),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode())
    prompt_id = result["prompt_id"]

    for _ in range(60):
        time.sleep(2)
        hist_req = urllib.request.Request(f"{COMFYUI_URL}/history/{prompt_id}")
        with urllib.request.urlopen(hist_req, timeout=15) as resp:
            hist = json.loads(resp.read().decode())
        if prompt_id in hist:
            outputs = hist[prompt_id]["outputs"]
            for node_out in outputs.values():
                if "images" in node_out:
                    img_info = node_out["images"][0]
                    view_url = f"{COMFYUI_URL}/view?filename={img_info['filename']}&subfolder={img_info.get('subfolder','')}&type={img_info.get('type','output')}"
                    with urllib.request.urlopen(view_url, timeout=15) as img_resp, open(out_path, "wb") as f:
                        f.write(img_resp.read())
                    return True
    return False


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
        category = p.get("categoryName", "")
        image_url = p.get("productImage", "")

        if not image_url:
            continue

        img_path = os.path.join(OUTPUT_DIR, f"tmp_{pid}.jpg")
        ass_path = os.path.join(OUTPUT_DIR, f"tmp_{pid}.ass")
        out_path = os.path.join(OUTPUT_DIR, f"short_{pid}.mp4")

        try:
            download_image(image_url, img_path)

            final_img_path = img_path
            mode = "제품샷"

            if should_use_realistic(category, name):
                mode = "실사"
                try:
                    ref_filename = upload_to_comfyui(img_path)
                    realistic_path = os.path.join(OUTPUT_DIR, f"tmp_realistic_{pid}.png")
                    ok = generate_realistic_model_image(ref_filename, name, realistic_path)
                    if ok:
                        final_img_path = realistic_path
                    else:
                        mode = "제품샷(실사 생성 실패로 대체)"
                except Exception as e:
                    mode = f"제품샷(실사 시도 중 에러: {e})"

            write_ass_subtitle(ass_path, name, price)
            make_short(final_img_path, ass_path, out_path)
            print(f"[완료:{mode}] {out_path}")

            if final_img_path != img_path and os.path.exists(final_img_path):
                os.remove(final_img_path)
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
