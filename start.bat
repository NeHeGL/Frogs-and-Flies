@echo off
echo Checking Python version...
python --version
if errorlevel 1 (
    echo.
    echo ERROR: Python not found. Please install Python 3.11, 3.12, or 3.13 from:
    echo https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)
echo.
echo Updating pip...
python -m pip install --upgrade pip
echo.
echo Installing pygame (pre-built binary only)...
python -m pip install --only-binary :all: pygame
if errorlevel 1 (
    echo.
    echo ERROR: No pre-built pygame available for your Python version.
    echo pygame supports Python 3.11, 3.12, and 3.13.
    echo Please install Python 3.13 from https://www.python.org/downloads/
    echo and re-run this script.
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
