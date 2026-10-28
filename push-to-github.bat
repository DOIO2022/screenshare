@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo Push LanShare to GitHub (account DOIO2022)
echo.

where git >nul 2>&1
if errorlevel 1 (
    echo Git not found. Install Git for Windows: https://git-scm.com/
    pause
    exit /b 1
)

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo Not a git repo. Run this inside the screenshare folder.
    pause
    exit /b 1
)

git remote remove origin 2>nul
git remote add origin https://github.com/DOIO2022/LanShare.git

echo Pushing main branch...
git push -u origin main
if errorlevel 1 (
    echo.
    echo If push failed: create empty repo at https://github.com/new named LanShare
    echo Then run this script again.
    pause
    exit /b 1
)

echo.
echo Done. Open: https://github.com/DOIO2022/LanShare/actions
echo Download Windows build from Artifacts when workflow finishes.
pause
