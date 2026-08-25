@echo off
echo Installing dependencies...
pip install -r requirements.txt
if %errorlevel% equ 0 (
    echo ✓ Installation successful
) else (
    echo ✗ Installation failed
    pause
)
