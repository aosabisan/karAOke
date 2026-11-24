@echo off
setlocal EnableExtensions
title Aosabi Karaoke
cd /d "%~dp0"
rem Aosabi Karaoke - Copyright (c) 2026 aosabi. All rights reserved.
rem Starts the program. The first time, it sets up a small private Python for it (nothing is installed system-wide).

set "UV=uv"
where uv >nul 2>nul
if errorlevel 1 (
  if exist "%USERPROFILE%\.local\bin\uv.exe" (
    set "UV=%USERPROFILE%\.local\bin\uv.exe"
  ) else (
    echo.
    echo  Aosabi Karaoke needs a small free helper tool called "uv" ^(by Astral^) to set up
    echo  its own private Python. It is downloaded from its official site, https://astral.sh/uv
    echo  and is not part of Aosabi Karaoke.
    echo.
    choice /c YN /m "Download and install uv now"
    if errorlevel 2 goto :nouv
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    if not exist "%USERPROFILE%\.local\bin\uv.exe" goto :nouv
    set "UV=%USERPROFILE%\.local\bin\uv.exe"
  )
)

set "ENVDIR=%LOCALAPPDATA%\AosabiKaraoke\program-env"
if not exist "%ENVDIR%\Scripts\python.exe" (
  echo.
  echo  First start: setting up Aosabi Karaoke's private Python ^(Python 3.12, plus the free
  echo  libraries numpy and aiohttp from the official Python package index^). About 150 MB, one time.
  echo.
  "%UV%" venv --python 3.12 "%ENVDIR%" || goto :failed
  "%UV%" pip install --python "%ENVDIR%\Scripts\python.exe" -r "app\requirements.txt" || goto :failed
)

set "PYTHONPATH=%~dp0app"
"%ENVDIR%\Scripts\python.exe" -m karaoke %*
if errorlevel 1 pause
exit /b

:nouv
echo.
echo  uv was not installed, so Aosabi Karaoke cannot start yet.
echo  You can install it yourself from https://docs.astral.sh/uv/ and start this file again.
pause
exit /b 1

:failed
echo.
echo  The setup did not finish. Check your internet connection and start this file again.
pause
exit /b 1
