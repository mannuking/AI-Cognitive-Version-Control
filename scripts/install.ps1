# =============================================================================
# CVC (Cognitive Version Control) — Installer for Windows PowerShell
# Usage:  irm https://jaimeena.com/cvc/install.ps1 | iex
# =============================================================================
$ErrorActionPreference = "Stop"

$PackageName  = "tm-ai[all]"
$PyPIName     = "tm-ai"          # name as uv tool list shows it
$ToolName     = "cvc"
$DisplayName  = "CVC — AI Cognitive Version Control"
$UvInstallUrl = "https://astral.sh/uv/install.ps1"

# ── Helpers ───────────────────────────────────────────────────────────────────
function Write-Step  ($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok    ($msg) { Write-Host " v  $msg" -ForegroundColor Green }
function Write-Fail  ($msg) { Write-Host " x  ERROR: $msg" -ForegroundColor Red }

# ── Banner ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ============================================" -ForegroundColor DarkCyan
Write-Host "    $DisplayName" -ForegroundColor Cyan
Write-Host "  ============================================" -ForegroundColor DarkCyan
Write-Host ""

# ── Step 1: Check / install uv ────────────────────────────────────────────────
Write-Step "Checking for uv package manager..."

$uvCmd = Get-Command uv -ErrorAction SilentlyContinue

if ($uvCmd) {
    $uvVersion = (uv --version 2>&1)[0]
    Write-Ok "uv already installed: $uvVersion"
} else {
    Write-Step "uv not found — installing uv (this will also manage Python for you)..."
    
    try {
        # Allow script execution for this process only (no system changes)
        Set-ExecutionPolicy Bypass -Scope Process -Force
        $uvScript = Invoke-RestMethod -Uri $UvInstallUrl
        Invoke-Expression $uvScript
    } catch {
        Write-Fail "Failed to install uv automatically."
        Write-Host ""
        Write-Host "  Please install uv manually from: https://docs.astral.sh/uv/getting-started/installation/"
        Write-Host "  Then re-run:  uv tool install tm-ai[all]"
        exit 1
    }

    # Refresh PATH for this session
    $env:PATH = [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + `
                [System.Environment]::GetEnvironmentVariable("Path", "Machine")

    $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uvCmd) {
        Write-Fail "uv installation failed. See https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    }
    Write-Ok "uv installed successfully"
}

# ── Step 2: Install / upgrade CVC ─────────────────────────────────────────────
Write-Step "Installing $DisplayName from PyPI..."

$toolList = uv tool list 2>&1
if ($toolList -match "(^|\s)$PyPIName(\s|@|$)") {
    Write-Step "Existing uv-managed installation found — upgrading..."
    uv tool upgrade $PyPIName
    Write-Ok "CVC upgraded to latest version"
} else {
    uv tool install $PackageName --python 3.11
    Write-Ok "CVC installed successfully"
}

# Ensure tool bin directory is on the user PATH
try { uv tool update-shell | Out-Null } catch {}

# ── Step 3: Verify & detect PATH conflicts ────────────────────────────────────
Write-Step "Verifying installation..."

# Refresh PATH for this session
$env:PATH = [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + `
            [System.Environment]::GetEnvironmentVariable("Path", "Machine")

# Locate the uv-managed cvc binary directly (source of truth)
$uvBinDir   = (uv tool bin 2>&1 | Select-Object -First 1).ToString().Trim()
$uvCvcPath  = Join-Path $uvBinDir "$ToolName.exe"

# Verify the uv-installed binary works and get its version
if (Test-Path $uvCvcPath) {
    $uvVersion = (& $uvCvcPath --version 2>&1) | Select-Object -First 1
    Write-Ok "uv-managed ${ToolName}: $uvVersion  [$uvCvcPath]"
} else {
    Write-Host "  Note: Could not locate uv-managed binary at $uvCvcPath" -ForegroundColor Yellow
}

# Check what 'cvc' resolves to in PATH — warn on conflict
$pathCvc = Get-Command $ToolName -ErrorAction SilentlyContinue
if ($pathCvc) {
    $pathCvcResolved = $pathCvc.Source
    if ($uvBinDir -and (-not $pathCvcResolved.StartsWith($uvBinDir, [System.StringComparison]::OrdinalIgnoreCase))) {
        Write-Host ""
        Write-Host "  ⚠  PATH CONFLICT DETECTED" -ForegroundColor Yellow
        Write-Host "     'cvc' in your PATH resolves to the OLD installation:" -ForegroundColor Yellow
        Write-Host "     $pathCvcResolved" -ForegroundColor Red
        Write-Host "     The NEW version is at:" -ForegroundColor Yellow
        Write-Host "     $uvCvcPath" -ForegroundColor Green
        Write-Host ""
        Write-Host "  To fix — uninstall the old version with ONE of these:" -ForegroundColor White
        Write-Host "    pip uninstall tm-ai -y" -ForegroundColor Cyan
        Write-Host "    pipx uninstall tm-ai" -ForegroundColor Cyan
        Write-Host "  Then open a new terminal and run 'cvc' — it will use 1.5.2." -ForegroundColor White
    }
} else {
    Write-Host ""
    Write-Host "  Note: Please open a new PowerShell window and run 'cvc --help'" -ForegroundColor Yellow
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Installation complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  Quick start:" -ForegroundColor White
Write-Host "    cvc --help              Show all commands" -ForegroundColor Cyan
Write-Host "    cvc init                Initialize CVC in your project" -ForegroundColor Cyan
Write-Host "    cvc launch claude       Launch Claude Code with time-machine" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Docs:  https://jaimeena.com/cvc" -ForegroundColor White
Write-Host "  Repo:  https://github.com/mannuking/AI-Cognitive-Version-Control" -ForegroundColor White
Write-Host ""
