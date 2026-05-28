@echo off
echo Checking Python version...
python --version
if errorlevel 1 (
    echo.
    echo ERROR: Python not found. Please install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)
echo.
echo Updating pip...
python -m pip install --upgrade pip
echo.
echo Installing pygame...
python -m pip install --only-binary :all: pygame
if errorlevel 1 (
    echo pygame not available for your Python version, trying pygame-ce...
    python -m pip install --only-binary :all: pygame-ce
    if errorlevel 1 (
        echo.
        echo ERROR: Could not install pygame or pygame-ce for your Python version.
        echo Please report this issue at https://github.com/NeHeGL/Frogs-and-Flies/issues
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
