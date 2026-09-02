; Genesis Phase 9 installer integration.
; Tauri injects this hook after application files and shortcuts are installed.
; The installer waits for the native Genesis setup window before completing.

!macro NSIS_HOOK_POSTINSTALL
  DetailPrint "Launching Genesis AI setup..."
  ExecWait '"$INSTDIR\${MAINBINARYNAME}.exe" --installer-setup' $0
  ${If} $0 != 0
    MessageBox MB_ICONEXCLAMATION|MB_OK "Genesis was installed, but AI setup did not finish successfully. You can launch Genesis from the Start menu to resume setup."
  ${EndIf}
!macroend
