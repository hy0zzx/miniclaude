; HopClaude Windows Installer (NSIS)
; Build: makensis installer\installer.nsi

!define APP_NAME     "HopClaude"
!define APP_VERSION  "1.0.0"
!define APP_PUBLISHER "HopClaude"
!define APP_EXE      "HopClaude.exe"
!define APP_ICON     "..\assets\icon.ico"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"

Name "${APP_NAME} ${APP_VERSION}"
OutFile "..\build\HopClaude-Setup-${APP_VERSION}-win.exe"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
InstallDirRegKey HKCU "Software\${APP_NAME}" "InstallDir"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

Icon "${APP_ICON}"
UninstallIcon "${APP_ICON}"

!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_ICON "${APP_ICON}"
!define MUI_UNICON "${APP_ICON}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY

Page custom AutostartPage AutostartPageLeave

!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Var AutostartCheck

Function AutostartPage
  nsDialogs::Create 1018
  Pop $0
  ${NSD_CreateCheckbox} 0 30u 100% 12u "Run HopClaude on Windows startup (recommended)"
  Pop $AutostartCheck
  ${NSD_SetState} $AutostartCheck ${BST_CHECKED}
  nsDialogs::Show
FunctionEnd

Function AutostartPageLeave
  ${NSD_GetState} $AutostartCheck $0
  StrCpy $AutostartCheck $0
FunctionEnd

Section "Main" SecMain
  SetOutPath "$INSTDIR"
  File "..\dist\${APP_EXE}"
  File "${APP_ICON}"

  WriteRegStr HKCU "Software\${APP_NAME}" "InstallDir" "$INSTDIR"

  ${If} $AutostartCheck == ${BST_CHECKED}
    WriteRegStr HKCU \
      "Software\Microsoft\Windows\CurrentVersion\Run" \
      "${APP_NAME}" '"$INSTDIR\${APP_EXE}"'
  ${EndIf}

  DetailPrint "Registering Claude Code hooks..."
  nsExec::ExecToLog '"$INSTDIR\${APP_EXE}" --setup'

  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortCut  "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" \
                  "$INSTDIR\${APP_EXE}" "" "$INSTDIR\icon.ico"
  CreateShortCut  "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk" \
                  "$INSTDIR\Uninstall.exe"

  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "DisplayName"     "${APP_NAME}"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "DisplayVersion"  "${APP_VERSION}"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "Publisher"       "${APP_PUBLISHER}"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKLM "${UNINSTALL_KEY}" "DisplayIcon"     "$INSTDIR\icon.ico"
SectionEnd

Section "Uninstall"
  DeleteRegValue HKCU \
    "Software\Microsoft\Windows\CurrentVersion\Run" "${APP_NAME}"

  Delete "$INSTDIR\${APP_EXE}"
  Delete "$INSTDIR\icon.ico"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir  "$INSTDIR"

  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk"
  RMDir  "$SMPROGRAMS\${APP_NAME}"

  DeleteRegKey HKCU  "Software\${APP_NAME}"
  DeleteRegKey HKLM  "${UNINSTALL_KEY}"
SectionEnd
