@echo off
cd /d "%~dp0"
echo Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Python not found. Please install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)
echo Updating pip...
python -m pip install --upgrade pip --quiet
echo Installing pygame...
python -m pip install --only-binary :all: pygame --quiet >nul 2>&1
if errorlevel 1 (
    python -m pip install --only-binary :all: pygame-ce --quiet
    if errorlevel 1 (
        echo.
        echo ERROR: Could not install pygame. Please report this at:
        echo https://github.com/NeHeGL/Frogs-and-Flies/issues
        pause
        exit /b 1
    )
)
echo.
echo Starting Frogs and Flies...
python main.py
if errorlevel 1 (
    echo.
    echo ERROR: Game exited with an error. See above for details.
    pause
)
