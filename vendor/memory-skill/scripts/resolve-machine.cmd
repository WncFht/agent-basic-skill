@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "RUNTIME=%SCRIPT_DIR%..\runtime\memory_runtime.py"

where py >nul 2>nul
if not errorlevel 1 (
  py -3 "%RUNTIME%" machine %*
  exit /b %errorlevel%
)

where python >nul 2>nul
if not errorlevel 1 (
  python "%RUNTIME%" machine %*
  exit /b %errorlevel%
)

echo memory runtime error 1>&2
echo What happened: Could not find a Python 3 interpreter for memory-skill. 1>&2
echo Why it matters: The memory runtime is implemented in Python so it can behave consistently on Windows, Linux, and macOS. 1>&2
echo How to fix: Install Python 3 and ensure `py -3` or `python` is available on PATH, then retry this command. 1>&2
exit /b 1
