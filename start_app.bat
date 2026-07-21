@echo off
setlocal
title Frogs and Flies

cd /d "%~dp0"

:: -- Make sure the virtual environment exists --------------------
if not exist ".venv\Scripts\python.exe" (
    echo  [INFO] Virtual environment not found. Running installer...
    echo.
    set FF_AUTO_INSTALL=1
    call "%~dp0install.bat"
    set FF_AUTO_INSTALL=
    if errorlevel 1 (
        echo  [ERROR] Installation failed. Fix the errors above and try again.
        pause
        exit /b 1
    )
)

echo.
echo Starting Frogs and Flies...
".venv\Scripts\python.exe" main.py
if errorlevel 1 (
    echo.
    echo ERROR: Game exited with an error. See above for details.
    pause
)
