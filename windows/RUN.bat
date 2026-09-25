@echo off
cd /d "%~dp0"
python --version >nul 2>&1 || (echo Install Python 3.10+ from python.org and tick "Add to PATH" & pause & exit)
python -m pip install --quiet psutil
start "" pythonw arenaboost.py
