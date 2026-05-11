# HopClaude.spec
# PyInstaller 빌드 설정 파일
# 실행: pyinstaller HopClaude.spec

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['src/widget.py'],
    pathex=[str(Path('.').resolve())],
    binaries=[],
    datas=[],
    hiddenimports=[
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtWidgets',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'PIL', 'webview'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='HopClaude',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # 콘솔 창 숨김
    icon='assets/icon.ico' if sys.platform == 'win32' else 'assets/icon.icns',
    codesign_identity=None,
    entitlements_file=None,
)

# macOS: .app 번들 생성
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='HopClaude.app',
        icon='assets/icon.icns',
        bundle_identifier='io.hopclaude.widget',
        info_plist={
            'NSHighResolutionCapable': True,
            'LSUIElement': True,          # Dock 아이콘 숨김 (백그라운드 앱)
            'CFBundleShortVersionString': '1.0.0',
            'CFBundleVersion': '1.0.0',
            'NSPrincipalClass': 'NSApplication',
        },
    )
