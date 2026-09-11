; Custom NSIS hooks for Code Agent installer.
; electron-builder merges this into the generated script.

!macro customInstall
  ; Ensure Start Menu / Desktop shortcuts are registered after files are copied.
!macroend

!macro customUnInstall
  ; Leave user data (workspaces, settings) unless deleteAppDataOnUninstall is enabled.
!macroend
