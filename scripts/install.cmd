@echo off
:: =============================================================================
:: CVC (Cognitive Version Control) — Installer for Windows CMD
:: Usage:  curl -fsSL https://jaimeena.com/cvc/install.cmd -o install.cmd && install.cmd
:: =============================================================================

echo.
echo   ============================================
echo     CVC -- AI Cognitive Version Control
echo   ============================================
echo.

:: Check if PowerShell is available (it always is on Windows 7+)
where powershell >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo  x  ERROR: PowerShell is not available on this system.
    echo     Please install CVC manually: pip install tm-ai[all]
    exit /b 1
)

echo =^> Launching PowerShell installer...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://jaimeena.com/cvc/install.ps1 | iex"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  x  Installation failed. Please try one of:
    echo     1. Open PowerShell and run:  irm https://jaimeena.com/cvc/install.ps1 ^| iex
    echo     2. Or run:  pip install tm-ai[all]
    exit /b 1
)

echo.
pause
