"""
HopClaude — Claude Code 응답 알림 위젯
메인 애플리케이션
"""

import hashlib
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 51234
EVENT_QUEUE: list[dict] = []
EVENT_LOCK = threading.Lock()

CREDENTIALS_PATH = os.path.join(os.path.expanduser("~"), ".claude", ".credentials.json")


# ---------------------------------------------------------------------------
# OAuth 인증 헬퍼
# ---------------------------------------------------------------------------

def read_access_token() -> str:
    """~/.claude/.credentials.json 에서 Claude OAuth 액세스 토큰을 읽음."""
    try:
        with open(CREDENTIALS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("claudeAiOauth", {}).get("accessToken", "")
    except Exception:
        return ""


def get_widget_secret() -> str:
    """액세스 토큰의 SHA-256 다이제스트를 공유 시크릿으로 반환.
    크리덴셜 파일이 없으면 빈 문자열을 반환 (인증 생략)."""
    token = read_access_token()
    if not token:
        return ""
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------------------
# 로컬 HTTP 서버
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def _json(self, code, payload):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def _verify_auth(self) -> bool:
        """Authorization 헤더를 검증.
        크리덴셜 파일이 없거나 토큰이 비어있으면 인증을 생략하고 통과."""
        expected = get_widget_secret()
        if not expected:
            return True
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return False
        provided = auth_header[len("Bearer "):]
        return provided == expected

    def do_GET(self):
        if self.path == "/pull":
            with EVENT_LOCK:
                events = list(EVENT_QUEUE)
                EVENT_QUEUE.clear()
            self._json(200, {"events": events})
        elif self.path == "/health":
            self._json(200, {"ok": True})
        else:
            self._json(404, {})

    def do_POST(self):
        if self.path != "/notify":
            self._json(404, {})
            return
        if not self._verify_auth():
            self._json(403, {"error": "unauthorized"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            body = {}
        with EVENT_LOCK:
            EVENT_QUEUE.append({
                "event":   body.get("event", "Stop"),
                "message": body.get("message", ""),
                "ts":      time.time(),
            })
        self._json(200, {"queued": True})

    def log_message(self, *_):
        pass


def run_server():
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    server.serve_forever()


def is_already_running() -> bool:
    """같은 포트에 이미 위젯 서버가 응답 중이면 True."""
    import urllib.request, urllib.error
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 자동 시작 등록 헬퍼
# ---------------------------------------------------------------------------

def get_exe_path() -> str:
    """PyInstaller 빌드 시 실행파일 경로, 개발 시 스크립트 경로 반환."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(__file__)


def register_autostart():
    exe = get_exe_path()
    if sys.platform == "win32":
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, "HopClaude", 0, winreg.REG_SZ, f'"{exe}"')
        winreg.CloseKey(key)
    elif sys.platform == "darwin":
        plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>io.hopclaude.widget</string>
  <key>ProgramArguments</key>
  <array><string>{exe}</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
</dict>
</plist>"""
        la_dir = os.path.expanduser("~/Library/LaunchAgents")
        os.makedirs(la_dir, exist_ok=True)
        plist_path = os.path.join(la_dir, "io.hopclaude.widget.plist")
        with open(plist_path, "w") as f:
            f.write(plist)
        os.system(f"launchctl load '{plist_path}'")


def register_hook():
    """~/.claude/settings.json 에 Stop / Notification 훅을 등록.
    기존 훅 목록에 추가하며, HopClaude 항목이 이미 있으면 갱신."""
    exe = get_exe_path()

    if getattr(sys, "frozen", False):
        cmd_stop   = f'"{exe}" --hook Stop'
        cmd_notify = f'"{exe}" --hook Notification'
    else:
        # 개발 모드: widget.py 자체를 --hook 모드로 직접 호출
        cmd_stop   = f'"{sys.executable}" "{exe}" --hook Stop'
        cmd_notify = f'"{sys.executable}" "{exe}" --hook Notification'

    candidates = [
        os.path.expanduser("~/.claude/settings.json"),
        os.path.expanduser("~/.config/claude/settings.json"),
    ]
    settings_path = next((p for p in candidates if os.path.exists(p)), candidates[0])
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)

    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except Exception:
        settings = {}

    def upsert_hook(event_hooks: list, cmd: str) -> list:
        """HopClaude 항목만 갱신하고 나머지 훅은 보존."""
        hopclaude_entry = {"matcher": "", "hooks": [
            {"type": "command", "command": cmd, "timeout": 5}
        ]}
        kept = [g for g in event_hooks
                if not any("--hook" in h.get("command", "") for h in g.get("hooks", []))]
        kept.append(hopclaude_entry)
        return kept

    hooks = settings.setdefault("hooks", {})
    hooks["Stop"]         = upsert_hook(hooks.get("Stop", []),         cmd_stop)
    hooks["Notification"] = upsert_hook(hooks.get("Notification", []), cmd_notify)

    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

    return settings_path


# ---------------------------------------------------------------------------
# PyQt6 위젯 창
# ---------------------------------------------------------------------------

def run_widget(sw: int, sh: int):
    import math as _math
    import time as _time

    from PyQt6.QtWidgets import QApplication, QWidget
    from PyQt6.QtCore import Qt, QTimer, QPoint, QRectF, QPointF
    from PyQt6.QtGui import (QColor, QPainter, QPainterPath, QBrush, QPen,
                              QFont, QFontDatabase, QFontMetrics,
                              QGuiApplication, QPolygonF)

    # ── 물리 상수 ──────────────────────────────────────────────────────────
    GRAVITY           = 0.0018   # px/ms²
    RESTITUTION_BIG   = 0.82
    RESTITUTION_SMALL = 0.52
    MIN_V             = 0.12
    MAX_H             = 44.0

    # ── 레이아웃 상수 ──────────────────────────────────────────────────────
    CHAR_W, CHAR_H = 86, 54
    W, H    = 140, 180          # 창 크기 — H를 넉넉히 잡아 말풍선 클리핑 방지
    PAD_B   = 16
    CHAR_X  = (W - CHAR_W) // 2                          # = 27
    CHAR_Y  = H - PAD_B - 6 - 4 - CHAR_H                # = 100  (쉬는 위치 상단)
    SHAD_CX = W // 2
    SHAD_CY = H - PAD_B - 3                              # = 161

    # ── 캐릭터 픽셀아트 ────────────────────────────────────────────────────
    CORAL = QColor(0xDA, 0x77, 0x57)
    WHITE = QColor(0xFF, 0xFF, 0xFF)
    _VW, _VH = 256.0, 160.0
    _sx = lambda v: round(v * CHAR_W / _VW)
    _sy = lambda v: round(v * CHAR_H / _VH)
    # 경계 좌표를 먼저 계산한 뒤 너비/높이를 차분으로 구해 1px 오차 누적 방지
    Xb = [_sx(v) for v in (0, 32, 64, 80, 176, 192, 225, 256)]
    Yb = [_sy(v) for v in (0, 32, 64, 96, 128, 160)]
    Lx = [_sx(v) for v in (48, 65, 80, 97, 160, 177, 192, 209)]
    RECTS = [
        (Xb[1], Yb[0], Xb[6]-Xb[1], Yb[1]-Yb[0], CORAL),  # 머리 상단 바
        (Xb[1], Yb[1], Xb[2]-Xb[1], Yb[2]-Yb[1], CORAL),  # 왼쪽 어깨
        (Xb[2], Yb[1], Xb[3]-Xb[2], Yb[2]-Yb[1], WHITE),  # 왼쪽 눈
        (Xb[3], Yb[1], Xb[4]-Xb[3], Yb[2]-Yb[1], CORAL),  # 코/입
        (Xb[4], Yb[1], Xb[5]-Xb[4], Yb[2]-Yb[1], WHITE),  # 오른쪽 눈
        (Xb[5], Yb[1], Xb[6]-Xb[5], Yb[2]-Yb[1], CORAL),  # 오른쪽 어깨
        (Xb[0], Yb[2], Xb[7]-Xb[0], Yb[3]-Yb[2], CORAL),  # 몸통
        (Xb[1], Yb[3], Xb[6]-Xb[1], Yb[4]-Yb[3], CORAL),  # 하체
        (Lx[0], Yb[4], Lx[1]-Lx[0], Yb[5]-Yb[4], CORAL),  # 왼발1
        (Lx[2], Yb[4], Lx[3]-Lx[2], Yb[5]-Yb[4], CORAL),  # 왼발2
        (Lx[4], Yb[4], Lx[5]-Lx[4], Yb[5]-Yb[4], CORAL),  # 오른발1
        (Lx[6], Yb[4], Lx[7]-Lx[6], Yb[5]-Yb[4], CORAL),  # 오른발2
    ]

    # ──────────────────────────────────────────────────────────────────────

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # ── 커스텀 폰트 로드 ──────────────────────────────────────────────────
    _base = (sys._MEIPASS if getattr(sys, "frozen", False)
             else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _font_path = os.path.join(_base, "assets", "fonts", "text",
                              "SF-Pro-Text-Medium.otf")
    _fid = QFontDatabase.addApplicationFont(_font_path)
    _families = QFontDatabase.applicationFontFamilies(_fid) if _fid >= 0 else []
    SPEECH_FONT_FAMILY = _families[0] if _families else "Segoe UI"

    screen = QGuiApplication.primaryScreen()
    if screen:
        g = screen.geometry()
        sw, sh = g.width(), g.height()

    class HopWidget(QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setFixedSize(W, H)
            self.move(sw - W - 30, sh - H - 60)

            self._y        = 0.0   # 점프 높이 (px 위쪽)
            self._vy       = 0.0
            self._bounces  = 0
            self._last_ms  = 0.0

            self._speech   = ""
            self._speech_a = 0     # 말풍선 불투명도 0-255

            self._drag_pos        = QPoint()
            self._waiting_for_click = False

            self._atimer = QTimer(self)
            self._atimer.setInterval(16)
            self._atimer.timeout.connect(self._step)

            self._ctimer = QTimer(self)   # 전역 마우스 클릭 감지
            self._ctimer.setInterval(50)
            self._ctimer.timeout.connect(self._check_click)

            self._ptimer = QTimer(self)
            self._ptimer.setInterval(700)
            self._ptimer.timeout.connect(self._poll)
            self._ptimer.start()

        # ── 애니메이션 ─────────────────────────────────────────────────────

        def _start_bounce(self):
            self._vy      = _math.sqrt(2 * GRAVITY * MAX_H)
            self._y       = 0.0
            self._bounces = 0
            self._last_ms = _time.monotonic() * 1000
            if not self._atimer.isActive():
                self._atimer.start()

        def _step(self):
            now = _time.monotonic() * 1000
            dt  = min(now - self._last_ms, 20)
            self._last_ms = now
            self._vy -= GRAVITY * dt
            self._y  += self._vy * dt
            if self._y <= 0:
                self._y = 0.0
                self._bounces += 1
                r = RESTITUTION_BIG if self._bounces <= 2 else RESTITUTION_SMALL
                self._vy = abs(self._vy) * r
                if self._vy < MIN_V:
                    self._y = 0.0
                    if self._waiting_for_click:
                        self._start_bounce()  # 전체 사이클 처음부터 반복
                    else:
                        self._atimer.stop()
            self.update()

        def trigger(self, event: str, message: str = ""):
            text = message or ("응답 도착!" if event == "Stop" else "확인 필요!")
            self._speech          = text
            self._speech_a        = 255
            self._waiting_for_click = True
            # 이전 클릭 누적값 소비 후 감지 시작
            if sys.platform == "win32":
                import ctypes
                ctypes.windll.user32.GetAsyncKeyState(0x01)  # 잔여 비트 초기화
            self._ctimer.start()
            self._start_bounce()
            self.update()

        def _check_click(self):
            if not self._waiting_for_click:
                self._ctimer.stop()
                return
            clicked = False
            if sys.platform == "win32":
                import ctypes
                # bit 0: 마지막 호출 이후 눌렸으면 1
                clicked = bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 1)
            if clicked:
                self._waiting_for_click = False
                self._ctimer.stop()
                self._speech_a = 0
                self.update()

        # ── 이벤트 폴링 ────────────────────────────────────────────────────

        def _make_conn(self):
            import http.client
            c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=1)
            return c

        def _poll(self):
            import json
            try:
                if not hasattr(self, "_conn") or self._conn is None:
                    self._conn = self._make_conn()
                try:
                    self._conn.request("GET", "/pull")
                    r = self._conn.getresponse()
                    data = r.read()
                except Exception:
                    # 연결이 끊겼으면 새로 만들어서 재시도
                    try: self._conn.close()
                    except Exception: pass
                    self._conn = self._make_conn()
                    self._conn.request("GET", "/pull")
                    r = self._conn.getresponse()
                    data = r.read()
                for ev in json.loads(data).get("events", []):
                    self.trigger(ev["event"], ev.get("message", ""))
            except Exception:
                try: self._conn.close()
                except Exception: pass
                self._conn = None

        # ── DWM 그림자/모서리 제거 ────────────────────────────────────────────

        def showEvent(self, ev):
            super().showEvent(ev)
            if sys.platform != "win32":
                return
            try:
                import ctypes
                hwnd = int(self.winId())
                # Windows 11 둥근 모서리 비활성화
                DWMWA_WINDOW_CORNER_PREFERENCE = 33
                DWMWCP_DONOTROUND = 1
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                    ctypes.byref(ctypes.c_int(DWMWCP_DONOTROUND)),
                    ctypes.sizeof(ctypes.c_int),
                )
                # DWM 비클라이언트 렌더링(그림자) 비활성화
                DWMWA_NCRENDERING_POLICY = 2
                DWMNCRP_DISABLED = 1
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, DWMWA_NCRENDERING_POLICY,
                    ctypes.byref(ctypes.c_int(DWMNCRP_DISABLED)),
                    ctypes.sizeof(ctypes.c_int),
                )
            except Exception:
                pass

        # ── 그리기 ─────────────────────────────────────────────────────────

        def paintEvent(self, _):
            from PyQt6.QtGui import QImage

            # 중간 버퍼에 그려서 프리멀티플라이드 알파 왜곡 방지
            buf = QImage(self.size(),
                         QImage.Format.Format_ARGB32_Premultiplied)
            buf.fill(Qt.GlobalColor.transparent)

            p = QPainter(buf)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)

            y_off = round(self._y)
            ratio = max(0.0, 1.0 - self._y / MAX_H)

            # 그림자
            sw_px   = round(20 + ratio * 34)
            s_alpha = round((0.05 + ratio * 0.13) * 255)
            p.setBrush(QBrush(QColor(0, 0, 0, s_alpha)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(
                QRectF(SHAD_CX - sw_px / 2, SHAD_CY - 3, sw_px, 6))

            # 캐릭터
            p.setPen(Qt.PenStyle.NoPen)
            ox, oy = CHAR_X, CHAR_Y - y_off
            for rx, ry, rw, rh, rc in RECTS:
                p.setBrush(QBrush(rc))
                p.drawRect(ox + rx, oy + ry, rw, rh)

            # 말풍선
            if self._speech and self._speech_a > 0:
                self._draw_speech(p)

            p.end()

            # 버퍼를 화면에 올림 (Source 모드로 투명 영역까지 덮어씀)
            sp = QPainter(self)
            sp.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_Source)
            sp.drawImage(0, 0, buf)
            sp.end()

        def _draw_speech(self, p: QPainter):
            a    = self._speech_a
            font = QFont(SPEECH_FONT_FAMILY, 9)
            p.setFont(font)
            fm   = QFontMetrics(font)
            tw   = fm.horizontalAdvance(self._speech)
            th   = fm.height()
            px, py = 10, 5
            bw, bh = tw + px * 2, th + py * 2
            cx     = W // 2

            # 캐릭터 최고점 위에 고정 배치 (점프해도 겹치지 않음)
            bot  = CHAR_Y - MAX_H - 10
            top  = bot - bh
            left = cx - bw // 2

            # 배경 둥근 사각형
            path = QPainterPath()
            path.addRoundedRect(QRectF(left, top, bw, bh), 7, 7)
            p.fillPath(path, QColor(255, 255, 255, a))
            p.setBrush(Qt.BrushStyle.NoBrush)   # 이전 coral brush가 남아 있으면 덮어씌워지므로 초기화
            p.setPen(QPen(QColor(0, 0, 0, min(a, 38)), 0.5))
            p.drawPath(path)

            # 꼬리 삼각형
            ts = 4
            tri = QPolygonF([
                QPointF(cx - ts, bot),
                QPointF(cx + ts, bot),
                QPointF(cx,      bot + ts),
            ])
            p.setBrush(QBrush(QColor(255, 255, 255, a)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPolygon(tri)

            # 텍스트
            p.setPen(QPen(QColor(26, 26, 26, a)))
            p.drawText(QRectF(left, top, bw, bh),
                       Qt.AlignmentFlag.AlignCenter, self._speech)

        # ── 마우스 이벤트 ──────────────────────────────────────────────────

        def mousePressEvent(self, ev):
            if ev.button() == Qt.MouseButton.LeftButton:
                self._drag_pos = (ev.globalPosition().toPoint()
                                  - self.frameGeometry().topLeft())

        def mouseMoveEvent(self, ev):
            if ev.buttons() == Qt.MouseButton.LeftButton:
                self.move(ev.globalPosition().toPoint() - self._drag_pos)

    widget = HopWidget()
    widget.show()
    sys.exit(app.exec())


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

def main():
    # --hook 모드: 설치된 단일 실행파일이 훅 스크립트 역할도 겸함
    if "--hook" in sys.argv:
        import urllib.request
        import urllib.error
        idx   = sys.argv.index("--hook")
        event = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "Stop"
        try:
            raw     = sys.stdin.read() or "{}"
            payload = json.loads(raw)
        except Exception:
            payload = {}
        message = payload.get("message", "응답 도착!" if event == "Stop" else "확인 필요!")[:40]
        body    = json.dumps({"event": event, "message": message}).encode()

        secret  = get_widget_secret()
        headers = {"Content-Type": "application/json"}
        if secret:
            headers["Authorization"] = f"Bearer {secret}"

        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/notify", data=body,
            headers=headers, method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=2)
        except urllib.error.URLError:
            pass
        return

    # --setup 모드: 설치 마법사에서 호출
    if "--setup" in sys.argv:
        register_autostart()
        path = register_hook()
        print(f"[HopClaude] 훅 등록 완료: {path}")
        print("[HopClaude] 자동 시작 등록 완료")
        return

    # 일반 위젯 실행 — 중복 실행 방지
    if is_already_running():
        sys.exit(0)

    threading.Thread(target=run_server, daemon=True).start()

    # HTTP 서버가 준비될 때까지 잠시 대기 후 창 실행
    import urllib.request, urllib.error
    for _ in range(10):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=0.3)
            break
        except Exception:
            time.sleep(0.1)

    # 화면 크기 감지 (Qt DPI 처리와 충돌하지 않도록 ctypes 직접 호출 생략)
    sw, sh = 1920, 1080
    try:
        if sys.platform == "darwin":
            from AppKit import NSScreen
            f = NSScreen.mainScreen().frame()
            sw, sh = int(f.size.width), int(f.size.height)
    except Exception:
        pass

    run_widget(sw, sh)


if __name__ == "__main__":
    main()
