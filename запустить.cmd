@echo off
rem ============================================================================
rem  Launch the project from a plain command prompt (cmd.exe).
rem
rem  Windows blocks .ps1 by default (ExecutionPolicy = Restricted), so this
rem  file is the most reliable entry point: it finds PowerShell and calls the
rem  main script with -ExecutionPolicy Bypass. Nothing is changed in the
rem  system - the policy applies to this single invocation only.
rem
rem  Usage:
rem    zapusk.cmd
rem    zapusk.cmd -BackendPort 8010 -FrontendPort 5180
rem    zapusk.cmd -NoBrowser
rem
rem  The file is deliberately ASCII-only (cmd.exe mixes codepages badly);
rem  all Russian messages are printed by the PowerShell script it starts.
rem ============================================================================

chcp 65001 >nul 2>nul
setlocal enableextensions
title kt6-protocol

pushd "%~dp0"
if errorlevel 1 (
    echo [ERROR] Cannot enter the project directory: %~dp0
    goto :fail
)

rem Find the launcher script next to this file (its name is Cyrillic, so we
rem take it from the directory listing instead of hard-coding it).
set "PS_SCRIPT="
for %%f in ("%~dp0*.ps1") do set "PS_SCRIPT=%%~ff"
if not defined PS_SCRIPT (
    echo [ERROR] No .ps1 launcher found in: %~dp0
    goto :fail
)

set "PS_EXE="
where pwsh.exe >nul 2>nul
if not errorlevel 1 set "PS_EXE=pwsh.exe"
if not defined PS_EXE (
    where powershell.exe >nul 2>nul
    if not errorlevel 1 set "PS_EXE=powershell.exe"
)
if not defined PS_EXE (
    echo [ERROR] Neither pwsh.exe nor powershell.exe is available in PATH.
    goto :fail
)

"%PS_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" goto :failed
popd
exit /b 0

:failed
echo.
echo ============================================================
echo  Launch failed with exit code %RC%.
echo  Read the messages above; server windows stay open on errors.
echo ============================================================
goto :fail

:fail
popd
if not defined NOPAUSE pause
exit /b 1
