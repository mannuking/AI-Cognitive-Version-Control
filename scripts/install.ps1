# =============================================================================
# CVC (Cognitive Version Control) — Installer for Windows PowerShell
# Usage:  irm https://jaimeena.com/cvc/install.ps1 | iex
# =============================================================================
# NOTE: Do NOT set $ErrorActionPreference = "Stop" here.
# uv writes non-error messages (e.g. "Nothing to upgrade") to stderr which
# would cause PowerShell to throw a terminating error before we can handle it.

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

    # Capture all output (stdout + stderr) without letting PowerShell throw
    $upgradeOut = (uv tool upgrade $PyPIName 2>&1) -join "`n"
    $upgradeOk  = $LASTEXITCODE -eq 0

    # "Nothing to upgrade" is written to stderr with exit code 1 — treat as success
    $nothingToUpgrade = $upgradeOut -match "Nothing to upgrade"

    if ($nothingToUpgrade -or $upgradeOk) {
        Write-Ok "CVC is already at the latest version"
    } elseif ($upgradeOut -match "being used by another process|os error 32|Failed to install entrypoint") {
        Write-Host ""
        Write-Host "  WARNING: CVC is currently running — the executable is locked." -ForegroundColor Yellow
        Write-Host "  The package was downloaded but the binary could not be replaced." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  Fix: Close all CVC windows / terminals, then re-run this installer." -ForegroundColor Cyan
        Write-Host "  (Or run:  uv tool upgrade tm-ai  after closing CVC)" -ForegroundColor Cyan
        Write-Host ""
    } else {
        # Unknown non-zero exit — show output but don't abort
        Write-Host "  Note: $upgradeOut" -ForegroundColor DarkGray
        Write-Ok "CVC install step completed"
    }
} else {
    uv tool install $PackageName --python 3.11
    Write-Ok "CVC installed successfully"
}

# Ensure tool bin directory is on the user PATH
try {
    uv tool update-shell 2>&1 | Out-Null
} catch {
    # ignore — non-critical
}

# ── Step 3: Verify & detect PATH conflicts ────────────────────────────────────
Write-Step "Verifying installation..."

# Refresh PATH for this session
$env:PATH = [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + `
            [System.Environment]::GetEnvironmentVariable("Path", "Machine")

# Locate the uv tool bin directory.
# Modern uv: "uv tool dir --bin"   Older uv: falls back to common default path.
$uvBinDir = $null
try {
    $dirOut = uv tool dir --bin 2>&1
    if ($LASTEXITCODE -eq 0 -and $dirOut) {
        $uvBinDir = ($dirOut -join '').Trim()
    }
} catch {
    # ignore — will use fallback path below
}

if (-not $uvBinDir) {
    # Fallback: uv's default bin dir on Windows is %USERPROFILE%\.local\bin
    $uvBinDir = Join-Path $env:USERPROFILE ".local\bin"
}

$uvCvcPath = Join-Path $uvBinDir "$ToolName.exe"

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
    $isSameAsUv = $uvBinDir -and `
        [System.IO.Path]::GetFullPath($pathCvcResolved).StartsWith(
            [System.IO.Path]::GetFullPath($uvBinDir),
            [System.StringComparison]::OrdinalIgnoreCase
        )
    if (-not $isSameAsUv) {
        Write-Host ""
        Write-Host "  WARNING: PATH CONFLICT DETECTED" -ForegroundColor Yellow
        Write-Host "     '$ToolName' in your PATH resolves to an OLD installation:" -ForegroundColor Yellow
        Write-Host "     $pathCvcResolved" -ForegroundColor Red
        Write-Host "     The NEW version is at:" -ForegroundColor Yellow
        Write-Host "     $uvCvcPath" -ForegroundColor Green
        Write-Host ""

        # Detect the source of the conflict and give a targeted fix
        if ($pathCvcResolved -match "conda") {
            Write-Host "  Detected source: Conda environment" -ForegroundColor White
            Write-Host "  Fix:" -ForegroundColor White
            Write-Host "    conda run pip uninstall tm-ai -y" -ForegroundColor Cyan
        } elseif ($pathCvcResolved -match "pipx") {
            Write-Host "  Detected source: pipx" -ForegroundColor White
            Write-Host "  Fix:" -ForegroundColor White
            Write-Host "    pipx uninstall tm-ai" -ForegroundColor Cyan
        } else {
            Write-Host "  Detected source: pip / system Python" -ForegroundColor White
            Write-Host "  Fix:" -ForegroundColor White
            Write-Host "    pip uninstall tm-ai -y" -ForegroundColor Cyan
        }
        Write-Host "  Then open a new terminal — 'cvc' will use $uvCvcPath" -ForegroundColor White
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
