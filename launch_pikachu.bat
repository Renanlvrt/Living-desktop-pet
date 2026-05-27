@echo off
cd /d "%~dp0"
python pikachu_widget.py
if errorlevel 1 (
    echo.
    echo ERROR: Could not launch widget.
    echo Make sure Python is installed and run:  pip install Pillow
    pause
)
