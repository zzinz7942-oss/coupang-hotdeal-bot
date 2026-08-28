"""
뮤직비디오용 씬 이미지 - 가벼운 생성(SD1.5, 저해상도) + RealESRGAN 4x 업스케일
- 1단계: SD1.5로 512x768 저해상도 빠른 생성 (VRAM/속도 부담 적음)
- 2단계: RealESRGAN_x4plus로 업스케일 (2048x3072까지 확보 가능)
"""

import json
import os
import time
import urllib.request

COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")


def generate_scene(prompt, negative_prompt="blurry, low quality, deformed, watermark, text", out_path=None,
                    width=512, height=768, steps=20, cfg=7.0, upscale=True):
    """가벼운 SD1.5 생성 + 선택적 RealESRGAN 업스케일"""
    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "v1-5-pruned-emaonly-fp16.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": prompt}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": negative_prompt}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0],
            "seed": int(time.time()), "steps": steps, "cfg": cfg,
            "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 1.0
        }},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
    }

    if upscale:
        workflow["7"] = {"class_type": "UpscaleModelLoader", "inputs": {"model_name": "RealESRGAN_x4plus.pth"}}
        workflow["8"] = {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["7", 0], "image": ["6", 0]}}
        final_image_node = "8"
    else:
        final_image_node = "6"

    workflow["9"] = {"class_type": "SaveImage", "inputs": {"images": [final_image_node, 0], "filename_prefix": "scene_lite"}}

    req = urllib.request.Request(
        f"{COMFYUI_URL}/prompt",
        data=json.dumps({"prompt": workflow}).encode(),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode())
    prompt_id = result["prompt_id"]

    for _ in range(90):
        time.sleep(2)
        hist_req = urllib.request.Request(f"{COMFYUI_URL}/history/{prompt_id}")
        with urllib.request.urlopen(hist_req, timeout=15) as resp:
            hist = json.loads(resp.read().decode())
        if prompt_id in hist:
            outputs = hist[prompt_id]["outputs"]
            for node_out in outputs.values():
                if "images" in node_out:
                    img_info = node_out["images"][0]
                    view_url = (
                        f"{COMFYUI_URL}/view?filename={img_info['filename']}"
                        f"&subfolder={img_info.get('subfolder','')}&type={img_info.get('type','output')}"
                    )
                    if out_path:
                        with urllib.request.urlopen(view_url, timeout=15) as img_resp, open(out_path, "wb") as f:
                            f.write(img_resp.read())
                    return True
    return False


if __name__ == "__main__":
    import sys
    prompt = sys.argv[1] if len(sys.argv) > 1 else "cinematic scene, ancient korean warrior, dramatic lighting, epic composition"
    out = sys.argv[2] if len(sys.argv) > 2 else "scene_test.png"
    ok = generate_scene(prompt, out_path=out)
    print("OK" if ok else "FAIL")
