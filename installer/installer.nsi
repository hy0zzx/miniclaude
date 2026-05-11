; HopClaude Windows 설치 마법사 (NSIS 스크립트)
; 빌드: makensis installer.nsi

!define APP_NAME     "HopClaude"
!define APP_VERSION  "1.0.0"
!define APP_PUBLISHER "HopClaude"
!define APP_EXE      "HopClaude.exe"
!define APP_ICON     "assets\icon.ico"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"

Name "${APP_NAME} ${APP_VERSION}"
OutFile "build\HopClaude-Setup-${APP_VERSION}-win.exe"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
InstallDirRegKey HKCU "Software\${APP_NAME}" "InstallDir"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

; 아이콘
Icon "${APP_ICON}"
UninstallIcon "${APP_ICON}"

; 페이지 구성
!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_ICON "${APP_ICON}"
!define MUI_UNICON "${APP_ICON}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY

; 자동 시작 옵션 페이지
Page custom AutostartPage AutostartPageLeave

!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Korean"

; 자동 시작 선택 변수
Var AutostartCheck

Function AutostartPage
  nsDialogs::Create 1018
  Pop $0
  ${NSD_CreateCheckbox} 0 30u 100% 12u "Windows 시작 시 자동으로 실행 (권장)"
  Pop $AutostartCheck
  ${NSD_SetState} $AutostartCheck ${BST_CHECKED}
  nsDialogs::Show
FunctionEnd

Function AutostartPageLeave
  ${NSD_GetState} $AutostartCheck $0
  StrCpy $AutostartCheck $0
FunctionEnd

Section "메인 설치" SecMain
  SetOutPath "$INSTDIR"
  File "dist\${APP_EXE}"
  File "${APP_ICON}"

  ; 설치 경로 레지스트리 저장
  WriteRegStr HKCU "Software\${APP_NAME}" "InstallDir" "$INSTDIR"

  ; 자동 시작 등록 (선택 시)
  ${If} $AutostartCheck == ${BST_CHECKED}
    WriteRegStr HKCU \
      "Software\Microsoft\Windows\CurrentVersion\Run" \
      "${APP_NAME}" '"$INSTDIR\${APP_EXE}"'
  ${EndIf}

  ; Claude Code 훅 자동 등록
  DetailPrint "Claude Code 훅을 등록하는 중..."
  nsExec::ExecToLog '"$INSTDIR\${APP_EXE}" --setup'

  ; 시작 메뉴 바로가기
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortCut  "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" \
                  "$INSTDIR\${APP_EXE}" "" "$INSTDIR\icon.ico"
  CreateShortCut  "$SMPROGRAMS\${APP_NAME}\제거.lnk" \
                  "$INSTDIR\Uninstall.exe"

  ; 제거 프로그램
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "DisplayName"     "${APP_NAME}"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "DisplayVersion"  "${APP_VERSION}"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "Publisher"       "${APP_PUBLISHER}"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKLM "${UNINSTALL_KEY}" "DisplayIcon"     "$INSTDIR\icon.ico"
SectionEnd

Section "Uninstall"
  ; 자동 시작 항목 제거
  DeleteRegValue HKCU \
    "Software\Microsoft\Windows\CurrentVersion\Run" "${APP_NAME}"

  ; 파일 제거
  Delete "$INSTDIR\${APP_EXE}"
  Delete "$INSTDIR\icon.ico"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir  "$INSTDIR"

  ; 시작 메뉴 제거
  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\제거.lnk"
  RMDir  "$SMPROGRAMS\${APP_NAME}"

  ; 레지스트리 정리
  DeleteRegKey HKCU  "Software\${APP_NAME}"
  DeleteRegKey HKLM  "${UNINSTALL_KEY}"
SectionEnd
