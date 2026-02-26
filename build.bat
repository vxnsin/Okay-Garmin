@echo off
echo ==============================
echo    Building Okay-Garmin...
echo ==============================

REM -----------------------------
REM Alte Builds löschen
REM -----------------------------
rmdir /s /q build
rmdir /s /q dist
del /q Okay-Garmin.zip

REM -----------------------------
REM PyInstaller Build
REM -----------------------------
echo.
echo ==============================
echo    Running PyInstaller...
echo ==============================
pyinstaller --onefile --noconsole ^
    --icon=icon.ico ^
    --add-data "web;web" ^
    main.py

REM -----------------------------
REM Release-Struktur erstellen
REM -----------------------------
echo.
echo ==============================
echo    Creating release structure...
echo ==============================
mkdir dist\sounds

REM Sounds kopieren (aus Projekt-Root!)
copy sounds\trigger.wav dist\sounds\
copy sounds\action.wav dist\sounds\

REM -----------------------------
REM ZIP erstellen
REM -----------------------------
echo.
echo ==============================
echo    Creating ZIP archive...
echo ==============================
powershell Compress-Archive ^
    -Path "dist\*" ^
    -DestinationPath "Okay-Garmin.zip"

echo.
echo ==============================
echo    DONE!
echo ==============================
pause