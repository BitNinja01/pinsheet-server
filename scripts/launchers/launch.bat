@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%..\.."

if not exist "%PROJECT_DIR%\.venv\" (
    echo Creating virtual environment...
    python -m venv "%PROJECT_DIR%\.venv"
)

call "%PROJECT_DIR%\.venv\Scripts\activate.bat"

if exist "%PROJECT_DIR%\requirements.txt" (
    pip install -q -r "%PROJECT_DIR%\requirements.txt"
)

if "%SECRET_KEY%"=="" (
    python -c "import secrets; print(secrets.token_hex(16))" > %TEMP%\psk.txt
    set /p SECRET_KEY=<%TEMP%\psk.txt
    del %TEMP%\psk.txt
)

python "%PROJECT_DIR%\source\main.py"
