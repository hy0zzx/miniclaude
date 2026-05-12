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
    """~/.claude/settings.json 에 Stop / Notification / PreToolUse 훅을 등록.
    기존 훅 목록에 추가하며, HopClaude 항목이 이미 있으면 갱신."""
    exe = get_exe_path()

    if getattr(sys, "frozen", False):
        cmd_stop     = f'"{exe}" --hook Stop'
        cmd_notify   = f'"{exe}" --hook Notification'
        cmd_pretool  = f'"{exe}" --hook PreToolUse'
    else:
        # 개발 모드: widget.py 자체를 --hook 모드로 직접 호출
        cmd_stop     = f'"{sys.executable}" "{exe}" --hook Stop'
        cmd_notify   = f'"{sys.executable}" "{exe}" --hook Notification'
        cmd_pretool  = f'"{sys.executable}" "{exe}" --hook PreToolUse'

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
    hooks["PreToolUse"]   = upsert_hook(hooks.get("PreToolUse", []),   cmd_pretool)

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
                              QFont, QFontDatabase, QFontMetrics, QPixmap,
                              QGuiApplication, QPolygonF)

    # ── 물리 상수 ──────────────────────────────────────────────────────────
    GRAVITY           = 0.0018   # px/ms²
    RESTITUTION_BIG   = 0.82
    RESTITUTION_SMALL = 0.52
    MIN_V             = 0.12
    MAX_H             = 44.0

    # ── 레이아웃 상수 ──────────────────────────────────────────────────────
    CHAR_W, CHAR_H = 86, 54
    W, H    = 220, 180          # 창 크기 — 말풍선 여유를 위해 W를 충분히 확보
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
    # 대시보드 서브위젯 ─────────────────────────────────────────────────────

    class _TickBar(QWidget):
        """세션 진행 바 (0/25/50/75/100 눈금 포함)."""
        def __init__(self):
            super().__init__()
            self._v = 0.0
            self.setFixedHeight(30)
        def setValue(self, v): self._v = max(0.0, min(100.0, v)); self.update()
        def paintEvent(self, _):
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            w, bh, by = self.width(), 6, 0
            p.setBrush(QBrush(QColor("#E0DDD8"))); p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(0, by, w, bh), 3, 3)
            if self._v > 0:
                p.setBrush(QBrush(QColor("#00875A")))
                p.drawRoundedRect(QRectF(0, by, w * self._v / 100, bh), 3, 3)
            font = QFont(SPEECH_FONT_FAMILY, 8); p.setFont(font)
            p.setPen(QPen(QColor("#AAAAAA")))
            for t in (0, 25, 50, 75, 100):
                tx = w * t / 100
                p.drawText(QRectF(tx - 14, by + bh + 3, 28, 14),
                           Qt.AlignmentFlag.AlignHCenter, str(t))
            p.end()

    class _SimpleBar(QWidget):
        """단순 둥근 진행 바."""
        def __init__(self):
            super().__init__()
            self._v = 0.0
            self.setFixedHeight(5)
        def setValue(self, v): self._v = max(0.0, min(100.0, v)); self.update()
        def paintEvent(self, _):
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            w, h = self.width(), self.height()
            p.setBrush(QBrush(QColor("#E0DDD8"))); p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(0, 0, w, h), h / 2, h / 2)
            if self._v > 0:
                p.setBrush(QBrush(QColor("#00875A")))
                p.drawRoundedRect(QRectF(0, 0, w * self._v / 100, h), h / 2, h / 2)
            p.end()

    class DashboardWindow(QWidget):
        """클릭 시 표시되는 사용량 대시보드 팝업."""

        def __init__(self):
            super().__init__()
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setFixedWidth(290)
            self._update_q: list = []
            self._syncing = False
            self._build_ui()

            self._q_timer = QTimer(self)
            self._q_timer.setInterval(80)
            self._q_timer.timeout.connect(self._drain_queue)
            self._q_timer.start()

            self._auto = QTimer(self)
            self._auto.setInterval(30_000)
            self._auto.timeout.connect(self.sync)

        # ── UI 구성 ────────────────────────────────────────────────────────

        def _build_ui(self):
            from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel,
                                          QFrame, QGraphicsDropShadowEffect)
            outer = QVBoxLayout(self)
            outer.setContentsMargins(10, 10, 10, 10)

            card = QFrame()
            card.setStyleSheet("QFrame{background:#EDE9E3;border-radius:14px;}")
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(20); shadow.setOffset(0, 4)
            shadow.setColor(QColor(0, 0, 0, 60))
            card.setGraphicsEffect(shadow)
            outer.addWidget(card)

            lay = QVBoxLayout(card)
            lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

            # ── 헤더 ──────────────────────────────────────────────────────
            hdr = QWidget(); hdr.setStyleSheet("background:transparent;")
            hl = QHBoxLayout(hdr); hl.setContentsMargins(14, 13, 14, 8); hl.setSpacing(6)

            # 픽셀 아이콘
            px = QPixmap(14, 14); px.fill(Qt.GlobalColor.transparent)
            pp = QPainter(px); pp.setPen(Qt.PenStyle.NoPen)
            pp.setBrush(QBrush(CORAL))
            for rx2, ry2, rw2, rh2 in [(2,0,10,2),(0,2,14,3),(2,5,10,3),(1,8,3,3),(5,8,3,3),(8,8,3,3),(11,8,3,3)]:
                pp.drawRect(rx2, ry2, rw2, rh2)
            pp.end()
            ico = QLabel(); ico.setPixmap(px)
            hl.addWidget(ico)

            ttl = QLabel("Claude 모니터")
            ttl.setFont(QFont(SPEECH_FONT_FAMILY, 11, QFont.Weight.Bold))
            ttl.setStyleSheet("color:#1A1A1A;background:transparent;")
            hl.addWidget(ttl)

            badge = QLabel("Max")
            badge.setFont(QFont(SPEECH_FONT_FAMILY, 9, QFont.Weight.Bold))
            badge.setStyleSheet("background:#DA7757;color:white;border-radius:4px;padding:1px 7px;")
            hl.addWidget(badge)
            hl.addStretch()
            lay.addWidget(hdr)

            def _section():
                f = QFrame()
                f.setStyleSheet("QFrame{background:white;border-radius:10px;margin:0 8px 6px 8px;}")
                return f

            # ── 현재 세션 카드 ─────────────────────────────────────────────
            sc = _section(); sl = QVBoxLayout(sc)
            sl.setContentsMargins(12, 10, 12, 12); sl.setSpacing(4)
            sr = QHBoxLayout()
            st = QLabel("현재 세션"); st.setFont(QFont(SPEECH_FONT_FAMILY, 11, QFont.Weight.DemiBold))
            st.setStyleSheet("color:#1A1A1A;background:transparent;")
            sr.addWidget(st); sr.addStretch()
            self._sess_pct = QLabel("—%")
            self._sess_pct.setFont(QFont(SPEECH_FONT_FAMILY, 16, QFont.Weight.Bold))
            self._sess_pct.setStyleSheet("color:#00875A;background:transparent;")
            sr.addWidget(self._sess_pct); sl.addLayout(sr)
            self._sess_bar = _TickBar(); sl.addWidget(self._sess_bar)
            self._sess_reset = QLabel("불러오는 중...")
            self._sess_reset.setFont(QFont(SPEECH_FONT_FAMILY, 9))
            self._sess_reset.setStyleSheet("color:#999;background:transparent;")
            sl.addWidget(self._sess_reset)
            lay.addWidget(sc)

            # ── 주간 사용량 카드 ───────────────────────────────────────────
            wc = _section(); wl = QVBoxLayout(wc)
            wl.setContentsMargins(12, 10, 12, 12); wl.setSpacing(5)
            wt = QLabel("주간 사용량"); wt.setFont(QFont(SPEECH_FONT_FAMILY, 11, QFont.Weight.DemiBold))
            wt.setStyleSheet("color:#1A1A1A;background:transparent;")
            wl.addWidget(wt)

            def _row(label_text):
                r = QHBoxLayout()
                lb = QLabel(label_text); lb.setFont(QFont(SPEECH_FONT_FAMILY, 10))
                lb.setStyleSheet("color:#555;background:transparent;")
                r.addWidget(lb); r.addStretch()
                pct = QLabel("—%"); pct.setFont(QFont(SPEECH_FONT_FAMILY, 10, QFont.Weight.Bold))
                pct.setStyleSheet("color:#00875A;background:transparent;")
                r.addWidget(pct)
                bar = _SimpleBar()
                return r, pct, bar

            r1, self._all_pct, self._all_bar = _row("전체 모델")
            wl.addLayout(r1); wl.addWidget(self._all_bar)
            r2, self._son_pct, self._son_bar = _row("Sonnet 전용")
            wl.addLayout(r2); wl.addWidget(self._son_bar)
            lay.addWidget(wc)

            # ── 푸터 ──────────────────────────────────────────────────────
            ft = QWidget(); ft.setStyleSheet("background:transparent;")
            fl = QHBoxLayout(ft); fl.setContentsMargins(14, 4, 14, 12); fl.setSpacing(8)
            self._sync_lbl = QLabel("동기화 안됨")
            self._sync_lbl.setFont(QFont(SPEECH_FONT_FAMILY, 9))
            self._sync_lbl.setStyleSheet("color:#AAA;background:transparent;")
            fl.addWidget(self._sync_lbl); fl.addStretch()
            for txt, fn in [("동기화", self.sync), ("닫기", self.hide)]:
                btn = QLabel(txt); btn.setFont(QFont(SPEECH_FONT_FAMILY, 9))
                btn.setStyleSheet("color:#DA7757;background:transparent;")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.mousePressEvent = (lambda _f=fn: lambda _: _f())()
                fl.addWidget(btn)
            lay.addWidget(ft)
            self.adjustSize()

        # ── 데이터 ────────────────────────────────────────────────────────

        def sync(self):
            if self._syncing:
                return
            self._syncing = True
            self._sync_lbl.setText("동기화 중...")
            import threading
            threading.Thread(target=self._bg_fetch, daemon=True).start()

        def _bg_fetch(self):
            try:
                import urllib.request
                token = read_access_token()
                if not token:
                    self._update_q.append(None); return
                req = urllib.request.Request(
                    "https://api.anthropic.com/api/oauth/usage",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "anthropic-client-type": "claude-code",
                        "anthropic-version": "2023-06-01",
                    },
                )
                r = urllib.request.urlopen(req, timeout=8)
                self._update_q.append(json.loads(r.read()))
            except Exception:
                self._update_q.append(None)

        def _drain_queue(self):
            if self._update_q:
                data = self._update_q.pop(0)
                self._syncing = False
                self._apply(data)

        def _apply(self, data):
            import datetime
            if data is None:
                self._sync_lbl.setText("동기화 실패"); return

            def _util(key):
                obj = data.get(key) or {}
                return obj.get("utilization") or 0.0

            def _reset_text(key):
                obj = data.get(key) or {}
                ra = obj.get("resets_at")
                if not ra:
                    return ""
                try:
                    dt = datetime.datetime.fromisoformat(ra)
                    sec = (dt - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
                    if sec <= 0:   return "곧 초기화"
                    if sec < 3600: return f"{int(sec/60)}분 후 초기화"
                    if sec < 86400: return f"{int(sec/3600)}시간 후 초기화"
                    return f"{int(sec/86400)}일 후 초기화"
                except Exception:
                    return ""

            sess = _util("five_hour")
            self._sess_pct.setText(f"{sess:.0f}%")
            self._sess_bar.setValue(sess)
            self._sess_reset.setText(_reset_text("five_hour"))

            all_u = _util("seven_day")
            self._all_pct.setText(f"{all_u:.0f}%")
            self._all_bar.setValue(all_u)

            son_u = _util("seven_day_sonnet")
            self._son_pct.setText(f"{son_u:.0f}%")
            self._son_bar.setValue(son_u)

            self._sync_lbl.setText("동기화됨")

        # ── 표시 ──────────────────────────────────────────────────────────

        def show_near(self, ref: QWidget):
            self.adjustSize()
            g = ref.frameGeometry()
            scr = QGuiApplication.primaryScreen().geometry()
            x = g.left() - self.width() - 8
            y = g.bottom() - self.height()
            self.move(
                max(0, min(x, scr.width() - self.width())),
                max(0, min(y, scr.height() - self.height() - 40)),
            )
            self.show(); self.raise_()
            self.sync()
            self._auto.start()

        def hide(self):
            self._auto.stop()
            super().hide()

        def keyPressEvent(self, ev):
            if ev.key() == Qt.Key.Key_Escape:
                self.hide()

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
            self._press_global    = QPoint()
            self._waiting_for_click = False
            self._dashboard       = DashboardWindow()

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

        def greet(self):
            """시작 시 한 번만 재생되는 인사 — 클릭 불필요, 2.5초 후 자동 소멸."""
            import random, datetime
            h = datetime.datetime.now().hour
            if 0 <= h < 5:
                pool = ["너무 졸려요...", "새벽에도 일해요?", "야근이에요?", "굿나잇 zzz"]
            elif 5 <= h < 11:
                pool = ["좋은 아침이에요!", "잘 주무셨어요?", "오늘도 화이팅!", "굿모닝~"]
            elif 11 <= h < 14:
                pool = ["점심은 드셨나요?", "맛있는 거 드세요!", "점심시간이에요~"]
            elif 14 <= h < 18:
                pool = ["오후도 화이팅!", "커피 한 잔 어때요?", "집중 잘 되고 있나요?"]
            elif 18 <= h < 21:
                pool = ["오늘도 수고하셨어요!", "저녁은 드셨나요?", "슬슬 마무리할 시간~"]
            else:
                pool = ["늦게까지 고생해요!", "오늘도 수고했어요 :)", "오늘도 잘 버텼어요!"]
            self._speech   = random.choice(pool)
            self._speech_a = 255
            self._start_bounce()
            self.update()
            QTimer.singleShot(2500, self._hide_greeting)

        def _hide_greeting(self):
            if not self._waiting_for_click:   # 그 사이 실제 알림이 안 왔으면
                self._speech_a = 0
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
            bw, bh = min(tw + px * 2, W - 8), th + py * 2
            cx     = W // 2

            # 캐릭터 최고점 위에 고정 배치 (점프해도 겹치지 않음)
            bot  = CHAR_Y - MAX_H - 10
            top  = bot - bh
            left = max(4, min(cx - bw // 2, W - bw - 4))

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
                self._press_global = ev.globalPosition().toPoint()
                self._drag_pos = (ev.globalPosition().toPoint()
                                  - self.frameGeometry().topLeft())

        def mouseMoveEvent(self, ev):
            if ev.buttons() == Qt.MouseButton.LeftButton:
                self.move(ev.globalPosition().toPoint() - self._drag_pos)

        def mouseReleaseEvent(self, ev):
            if ev.button() == Qt.MouseButton.LeftButton:
                delta = ev.globalPosition().toPoint() - self._press_global
                if delta.manhattanLength() < 6:
                    if self._dashboard.isVisible():
                        self._dashboard.hide()
                    else:
                        self._dashboard.show_near(self)

    widget = HopWidget()
    widget.show()
    QTimer.singleShot(400, widget.greet)   # 창 뜨고 0.4초 후 인사
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
        if event == "PreToolUse":
            tool = payload.get("tool_name", "tool")
            message = f"{tool} 승인 필요"
        else:
            message = payload.get("message", "응답 도착!" if event == "Stop" else "확인 필요!")
        message = message[:40]
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
