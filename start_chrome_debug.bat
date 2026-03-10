@echo off
echo Zaviram jakykoliv bezici Chrome, aby se mohl spustit v rezimu ladeni...
taskkill /F /T /IM chrome.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo Spoustim Google Chrome s CDP portem 9222...
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-allow-origins="*" --user-data-dir="%LOCALAPPDATA%\Google\Chrome\User Data"
) else (
    start "" "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-allow-origins="*" --user-data-dir="%LOCALAPPDATA%\Google\Chrome\User Data"
)

echo Chrome spusten! Nyni muzes pustit Jeeves bota.
timeout /t 3 /nobreak >nul
