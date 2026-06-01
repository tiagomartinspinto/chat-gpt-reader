@echo off
setlocal
set "BUNDLED=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%BUNDLED%" (
  set "PYTHON_EXE=%BUNDLED%"
) else (
  set "PYTHON_EXE=python"
)
"%PYTHON_EXE%" "%~dp0tools\build_index.py" %*
