@echo off
REM HopClaude Windows 빌드 스크립트
REM 실행 전 확인사항:
REM   1. pip install pyinstaller PyQt6 PyQt6-WebEngine pywin32
REM   2. NSIS 설치 (https://nsis.sourceforge.io)
REM   3. assets\icon.ico 파일 준비

echo [1/4] 의존성 설치 중...
pip install pyinstaller PyQt6 PyQt6-WebEngine pywin32 --quiet

echo [2/4] PyInstaller 빌드 중...
pyinstaller HopClaude.spec --clean --noconfirm
if errorlevel 1 (
    echo [오류] PyInstaller 빌드 실패
    pause
    exit /b 1
)

echo [3/4] NSIS 설치 마법사 빌드 중...
where makensis >nul 2>&1
if errorlevel 1 (
    echo [경고] NSIS를 찾을 수 없습니다. https://nsis.sourceforge.io 에서 설치 후 다시 실행하세요.
    echo        .exe 실행파일은 dist\HopClaude.exe 에 있습니다.
) else (
    makensis installer\installer.nsi
    if errorlevel 1 (
        echo [오류] NSIS 빌드 실패
        pause
        exit /b 1
    )
    echo [완료] build\HopClaude-Setup-1.0.0-win.exe 생성 완료
)

echo [4/4] 완료!
echo.
echo 배포 파일: build\HopClaude-Setup-1.0.0-win.exe
pause
