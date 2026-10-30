@echo off
REM CodeQuest one-click start for Windows. Double-click this file.
REM First run: creates a virtual environment, installs packages and loads demo data (a few minutes).
REM Later runs: starts straight away. Close this window or press Ctrl+C to stop.
setlocal
cd /d "%~dp0"
set URL=http://localhost:5000

set PY=
where py >nul 2>nul && py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set PY=py -3
if not defined PY (
  where python >nul 2>nul && python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set PY=python
)
if not defined PY (
  echo Python 3.10 or newer is required.
  echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH", then run this again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo ==^> Creating virtual environment ^(first run only^)
  %PY% -m venv .venv || goto :fail
)
set VPY=.venv\Scripts\python.exe

if not exist ".venv\.installed" (
  echo ==^> Installing packages ^(first run takes a few minutes^)
  "%VPY%" -m pip install --upgrade pip -q
  "%VPY%" -m pip install -r requirements.txt -q || goto :fail
  echo done> ".venv\.installed"
)

if not exist "learnopt.db" (
  echo ==^> Loading questions, coding problems and demo students ^(first run only^)
  "%VPY%" manage.py demo || goto :fail
)

echo.
echo   CodeQuest is starting at %URL%
echo   Demo logins ^(password demo123^): student@demo.local  ^|  instructor@demo.local
echo   Sign-up codes appear in this window. Press Ctrl+C to stop.
echo.

start "" cmd /c "timeout /t 4 /nobreak >nul & start "" %URL%"
"%VPY%" run.py
goto :eof

:fail
echo.
echo Something went wrong. Scroll up to see the error, or send it to Claude.
pause
exit /b 1
