"""
HopClaude 데모 트리거 — 실행 중인 위젯에 테스트 이벤트를 자동으로 전송합니다.
사용법: python demo_trigger.py
"""

import json
import sys
import time
import urllib.request
import urllib.error

PORT = 51234
BASE = f"http://127.0.0.1:{PORT}"

DEMO_SEQUENCE = [
    (1.5,  "Stop",         "응답 도착!"),
    (3.0,  "Notification", "확인 필요!"),
    (2.5,  "Stop",         "코드 작성 완료"),
    (3.5,  "Notification", "파일 쓰기 허용?"),
    (2.0,  "Stop",         "작업 완료!"),
    (4.0,  "Notification", "권한 확인 필요"),
    (2.0,  "Stop",         "응답 도착!"),
]


def check_health() -> bool:
    try:
        resp = urllib.request.urlopen(f"{BASE}/health", timeout=2)
        return resp.status == 200
    except urllib.error.URLError:
        return False


def send_event(event: str, message: str) -> bool:
    body = json.dumps({"event": event, "message": message}).encode()
    req = urllib.request.Request(
        f"{BASE}/notify", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=2)
        return resp.status == 200
    except urllib.error.URLError:
        return False


def main():
    print("HopClaude 데모 트리거")
    print(f"위젯 서버 연결 확인 중 (포트 {PORT})...")

    if not check_health():
        print(f"\n[오류] 위젯이 실행 중이지 않습니다.")
        print("먼저 위젯을 실행하세요: python src/widget.py")
        sys.exit(1)

    print("위젯 연결 성공!\n")
    print(f"{'이벤트':<16} {'메시지':<20} {'결과'}")
    print("-" * 50)

    for i, (delay, event, message) in enumerate(DEMO_SEQUENCE, 1):
        time.sleep(delay)
        ok = send_event(event, message)
        status = "전송 완료" if ok else "전송 실패"
        label = "✅" if event == "Stop" else "🔔"
        print(f"{label} {event:<14} {message:<20} {status}")

    print("\n데모 완료.")


if __name__ == "__main__":
    main()
