@echo off
REM Setup script for Hero's Journey SQL Assistant (Windows)

echo ==================================
echo Hero's Journey SQL Assistant Setup
echo ==================================
echo.

REM Check Python
echo Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    exit /b 1
)

python --version
echo.

REM Create virtual environment
echo Creating virtual environment...
if exist venv (
    echo Virtual environment already exists, skipping...
) else (
    python -m venv venv
    echo Virtual environment created
)
echo.

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install dependencies
echo.
echo Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo Error: Failed to install dependencies
    exit /b 1
)
echo Dependencies installed
echo.

REM Create .env file
if not exist .env (
    echo Creating .env file from template...
    copy .env.example .env
    echo .env file created
    echo Please edit .env file with your actual credentials
) else (
    echo .env file already exists
)
echo.

REM Check directories
echo Checking required directories...
if not exist docs (
    echo Error: docs\ directory not found
    exit /b 1
)
if not exist docs\tables (
    echo Error: docs\tables\ directory not found
    exit /b 1
)
echo Required directories present
echo.

REM Test imports
echo Testing imports...
python -c "from core import SchemaLoader, SQLGenerator, DatabaseManager, ExcelGenerator" 2>nul
if errorlevel 1 (
    echo Warning: Could not import all core modules
    echo This may be normal if dependencies are still installing
) else (
    echo Core modules import successfully
)
echo.

REM Summary
echo ==================================
echo Setup completed successfully!
echo ==================================
echo.
echo Next steps:
echo 1. Edit .env file with your credentials:
echo    notepad .env
echo.
echo 2. Activate virtual environment:
echo    venv\Scripts\activate
echo.
echo 3. Run Slack bot:
echo    python app.py
echo.
echo 4. Or run MCP server:
echo    python mcp_server.py
echo.
echo For production deployment, see DEPLOYMENT.md
echo.
pause
