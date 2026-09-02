; Genesis Phase 9 installer integration.
; Interactive installs wait for the native Genesis setup window before completing,
; then launch Genesis immediately into the configured Workbench.
; Silent installs skip the wizard and launch; first app launch resumes setup instead.

!macro NSIS_HOOK_POSTINSTALL
  IfSilent genesis_setup_skip 0
  DetailPrint "Launching Genesis AI setup..."
  ExecWait '"$INSTDIR\${MAINBINARYNAME}.exe" --installer-setup' $0
  ${If} $0 == 0
    DetailPrint "Genesis setup complete. Opening Workbench..."
    Exec '"$INSTDIR\${MAINBINARYNAME}.exe"'
  ${Else}
    MessageBox MB_ICONEXCLAMATION|MB_OK "Genesis was installed, but AI setup did not finish successfully. You can launch Genesis from the Start menu to resume setup."
  ${EndIf}
  genesis_setup_skip:
!macroend
