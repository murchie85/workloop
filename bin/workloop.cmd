@echo off
rem Windows launcher. Put this folder on PATH, then run: workloop
set PYTHONUTF8=1
if exist "%~dp0..\.venv\Scripts\python.exe" (
  "%~dp0..\.venv\Scripts\python.exe" "%~dp0workloop" %*
) else (
  python "%~dp0workloop" %*
)
