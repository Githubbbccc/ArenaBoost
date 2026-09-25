@echo off
cd /d "%~dp0"
python -m pip install --quiet psutil pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --uac-admin --name ArenaBoost arenaboost.py
echo.
echo Done! Your app is in the "dist" folder: dist\ArenaBoost.exe
pause
