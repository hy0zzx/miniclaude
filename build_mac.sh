#!/bin/bash
# HopClaude macOS 빌드 스크립트
# 실행 전 확인사항:
#   1. pip install pyinstaller pywebview pyobjc
#   2. brew install create-dmg  (DMG 생성용)
#   3. assets/icon.icns 파일 준비

set -e

echo "[1/4] 의존성 설치 중..."
pip install pyinstaller pywebview pyobjc --quiet

echo "[2/4] PyInstaller 빌드 중..."
pyinstaller HopClaude.spec --clean --noconfirm

if [ ! -d "dist/HopClaude.app" ]; then
    echo "[오류] HopClaude.app 생성 실패"
    exit 1
fi

echo "[3/4] DMG 패키징 중..."
mkdir -p build

if command -v create-dmg &> /dev/null; then
    create-dmg \
        --volname "HopClaude" \
        --volicon "assets/icon.icns" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 100 \
        --icon "HopClaude.app" 175 190 \
        --hide-extension "HopClaude.app" \
        --app-drop-link 425 190 \
        "build/HopClaude-1.0.0-mac.dmg" \
        "dist/"
    echo "[완료] build/HopClaude-1.0.0-mac.dmg 생성 완료"
else
    echo "[경고] create-dmg를 찾을 수 없습니다."
    echo "       brew install create-dmg 후 다시 실행하거나,"
    echo "       dist/HopClaude.app 을 직접 Applications 폴더에 복사하세요."
fi

echo "[4/4] 완료!"
echo ""
echo "배포 파일: build/HopClaude-1.0.0-mac.dmg"
echo ""
echo "※ 처음 실행 시 macOS 보안 경고가 뜨면:"
echo "   시스템 설정 → 개인정보 보호 및 보안 → '확인 없이 열기' 클릭"
