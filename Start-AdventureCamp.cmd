@echo off
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-AdventureCamp.ps1" %*
exit /b %errorlevel%
