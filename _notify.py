"""철물봇(@chulmool_bot) 채널로 승인요청/완료보고를 보내는 공용 헬퍼"""
import json
import urllib.request
import urllib.parse

KEYS_FILE = r"G:\내 드라이브\AI_JARVIS\AI_JARVIS_AGENT\keys.json"


def send(text: str):
    with open(KEYS_FILE, "r", encoding="utf-8") as f:
        keys = json.load(f)
    token = keys["TELEGRAM_BOT_TOKEN"]
    chat_id = keys["TELEGRAM_CHAT_ID"]
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


if __name__ == "__main__":
    import sys
    send(sys.argv[1] if len(sys.argv) > 1 else "테스트 메시지")
