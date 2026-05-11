# HopClaude

Claude Code가 응답을 마치거나 권한 확인을 기다릴 때, 모니터 우측 하단의 미니 클로드 캐릭터가 점프하며 알려주는 데스크톱 위젯입니다.

**Windows · macOS 모두 지원합니다.**

---

## 동작 방식

| 상태 | 캐릭터 색 | 말풍선 |
|---|---|---|
| 대기 중 | 코랄 (기본) | — |
| 응답 완료 (Stop) | 초록 | "응답 도착!" |
| 권한 확인 대기 (Notification) | 주황 | "확인 필요!" |

- 캐릭터를 **클릭**하면 5초간 반투명으로 숨겨집니다
- 창을 **드래그**해서 원하는 위치로 옮길 수 있습니다
- 설치 시 **부팅할 때 자동 실행** + **Claude Code 훅 자동 등록**됩니다

---

## 설치 (사용자용)

### Windows

1. `HopClaude-Setup-1.0.0-win.exe` 실행
2. 설치 마법사 안내에 따라 진행
3. "Windows 시작 시 자동으로 실행" 체크 유지 (권장)
4. 설치 완료 — 위젯이 바로 실행되고 Claude Code 훅도 자동 등록됩니다

### macOS

1. `HopClaude-1.0.0-mac.dmg` 열기
2. `HopClaude.app`을 `Applications` 폴더로 드래그
3. 처음 실행 시 보안 경고가 뜨면: `시스템 설정 → 개인정보 보호 및 보안 → 확인 없이 열기`
4. 앱이 실행되면 자동 시작과 훅 등록이 자동으로 처리됩니다

---

## 빌드 (개발자용)

### 폴더 구조

```
hopclaude/
├── src/
│   └── widget.py          메인 위젯 + 훅 수신 + 설정 등록 통합
├── installer/
│   └── installer.nsi      NSIS Windows 설치 마법사 스크립트
├── assets/
│   ├── icon.ico            Windows 아이콘 (256×256 이상 권장)
│   └── icon.icns           macOS 아이콘
├── HopClaude.spec          PyInstaller 빌드 설정
├── build_windows.bat       Windows 빌드 스크립트
├── build_mac.sh            macOS 빌드 스크립트
└── README.md
```

### Windows 빌드

```bash
# 아이콘 파일 준비 후
build_windows.bat
# → build/HopClaude-Setup-1.0.0-win.exe 생성
```

NSIS가 설치되어 있지 않으면 `dist/HopClaude.exe` 만 생성됩니다.
NSIS 다운로드: https://nsis.sourceforge.io

### macOS 빌드

```bash
chmod +x build_mac.sh
./build_mac.sh
# → build/HopClaude-1.0.0-mac.dmg 생성
```

`create-dmg`가 없으면 `dist/HopClaude.app` 만 생성됩니다.
```bash
brew install create-dmg   # 없는 경우
```

---

## 아이콘 준비

`assets/` 폴더에 아이콘 파일이 필요합니다.

**Windows** (`icon.ico`): 256×256 PNG를 ICO로 변환
```bash
# Python 으로 변환
pip install Pillow
python -c "from PIL import Image; img=Image.open('icon.png'); img.save('assets/icon.ico', sizes=[(256,256),(128,128),(64,64),(32,32),(16,16)])"
```

**macOS** (`icon.icns`): iconutil 사용
```bash
mkdir icon.iconset
sips -z 1024 1024 icon.png --out icon.iconset/icon_512x512@2x.png
sips -z 512  512  icon.png --out icon.iconset/icon_512x512.png
sips -z 256  256  icon.png --out icon.iconset/icon_256x256.png
sips -z 128  128  icon.png --out icon.iconset/icon_128x128.png
iconutil -c icns icon.iconset -o assets/icon.icns
```

---

## 포트 변경

기본 포트는 `51234`입니다. 충돌이 있을 경우 `src/widget.py` 상단의 `PORT` 값을 변경하고 다시 빌드하세요.

---

## 자주 묻는 질문

**Q. 위젯이 안 보여요.**
A. 멀티 모니터 환경에서 좌표가 어긋날 수 있습니다. `src/widget.py`의 `x`, `y` 계산 부분에서 오프셋을 조정하고 다시 빌드하세요.

**Q. Claude Code 훅이 등록됐는지 확인하고 싶어요.**
A. `~/.claude/settings.json`(macOS) 또는 `%USERPROFILE%\.claude\settings.json`(Windows)을 열어 `Stop`, `Notification` 항목이 있으면 정상입니다.

**Q. 훅을 수동으로 제거하고 싶어요.**
A. `settings.json`에서 `hooks` 블록 안의 `Stop`, `Notification` 항목을 삭제하시면 됩니다.

**Q. 응답 시작 알림도 추가하고 싶어요.**
A. `settings.json`에 `UserPromptSubmit` 훅을 추가하고, `widget.py`의 trigger 함수에 해당 이벤트 처리를 추가한 뒤 다시 빌드하시면 됩니다.
