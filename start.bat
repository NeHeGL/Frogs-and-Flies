@echo off
echo Updating pip...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo.
    echo ERROR: Could not update pip. Make sure Python 3.11+ is installed and in your PATH.
    echo Download Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)
echo.
echo Installing dependencies...
pip install pygame
if errorlevel 1 (
    echo.
    echo ERROR: Failed to install pygame. See above for details.
    pause
    exit /b 1
)
echo.
echo Starting Frogs and Flies...
python main.py
if errorlevel 1 (
    echo.
    echo ERROR: Game exited with an error. See above for details.
    pause
)
