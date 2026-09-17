<#
.SYNOPSIS
    Sets up SAP Incident Lab on a Windows machine: uv, Ollama + qwen3.8, the
    repo itself, the data directories, and the Claude Desktop registration.

.DESCRIPTION
    Mirrors the manual steps in DESIGN.md sections 10-11. Safe to re-run:
    each step checks what's already there before acting, the repo is pulled
    rather than re-cloned if it exists, and the Desktop config is merged
    (never overwritten) with a timestamped backup taken first.

    Leaves existing evidence and other MCP servers intact. Runs the full test
    suite once, including Windows-specific tests. Stops on failed verification.
    The shared Python setup command backs up and merges Desktop configuration.

.PARAMETER RepoUrl
    Git URL to clone/pull. Defaults to the private GitHub repo; you need SSH
    access configured on this machine (an SSH key registered with GitHub) for
    the default URL to work non-interactively.

.PARAMETER InstallDir
    Where the repo lives. Default: $env:USERPROFILE\sap-incident-lab

.PARAMETER DataDir
    Where incident evidence and job output live -- kept outside the repo on
    purpose (DESIGN.md section 5). Default: $env:USERPROFILE\SAPIncidentLabData

.PARAMETER Model
    Ollama model tag to pull. Default: qwen3.8. Pass another tag when the
    machine has less memory, for example qwen3.5:9b.

.PARAMETER FallbackModel
    Optional model tag to use if the primary model is missing. It is pulled
    and recorded explicitly; default: none.

.PARAMETER SkipTests
    Skip the `uv run pytest` verification step after installing dependencies.

.EXAMPLE
    .\setup-windows.ps1
    .\setup-windows.ps1 -InstallDir 'D:\dev\sap-incident-lab' -SkipTests
#>

[CmdletBinding()]
param(
    [string]$RepoUrl = 'git@github.com:bruce-hoppe_uoft/sap-incident-lab.git',
    [string]$InstallDir = (Join-Path $env:USERPROFILE 'sap-incident-lab'),
    [string]$DataDir = (Join-Path $env:USERPROFILE 'SAPIncidentLabData'),
    [string]$Model = 'qwen3.8',
    [string]$FallbackModel = '',
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'

function Write-Step {
    param([string]$Text)
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Write-Warn {
    param([string]$Text)
    Write-Host "    WARNING: $Text" -ForegroundColor Yellow
}

function Test-CommandExists {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

# ---------------------------------------------------------------------------
Write-Step "Checking prerequisite (git)"

foreach ($cmd in @('git')) {
    if (-not (Test-CommandExists $cmd)) {
        throw "'$cmd' is not on PATH. Install it first, then re-run this script."
    }
    $version = & $cmd --version
    if ($LASTEXITCODE -ne 0) { throw "$cmd --version failed." }
    Write-Host "    $cmd -> $version"
}

# ---------------------------------------------------------------------------
Write-Step "Checking uv (installs it if missing)"

if (-not (Test-CommandExists 'uv')) {
    Write-Host "    uv not found; installing via the official installer script..."
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression

    # The installer doesn't update the current session's PATH; the default
    # install location is what DESIGN.md and the official docs both assume.
    $uvBin = Join-Path $env:USERPROFILE '.local\bin'
    if (Test-Path $uvBin) {
        $env:PATH = "$uvBin;$env:PATH"
    }
    if (-not (Test-CommandExists 'uv')) {
        throw "uv installed but is still not on PATH. Open a new PowerShell window and re-run this script."
    }
}
$uvPath = (Get-Command uv).Source
Write-Host "    uv -> $uvPath"

# ---------------------------------------------------------------------------
Write-Step "Checking Ollama"

if (-not (Test-CommandExists 'ollama')) {
    Write-Warn "Ollama is not on PATH."
    if (Test-CommandExists 'winget') {
        Write-Host "    Attempting 'winget install Ollama.Ollama' ..."
        try {
            winget install --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
            if ($LASTEXITCODE -ne 0) { throw "winget install failed (exit code $LASTEXITCODE)." }
            $env:PATH = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
        } catch {
            Write-Warn "winget install failed: $($_.Exception.Message)"
        }
    }
    if (-not (Test-CommandExists 'ollama')) {
        Write-Warn "Install Ollama manually from https://ollama.com/download/windows, open a new PowerShell window, then re-run this script to continue from here."
        throw "Ollama is required before continuing."
    }
}
Write-Host "    ollama -> $(ollama --version)"

Write-Step "Pulling model '$Model' (this can take a while on first run)"
ollama pull $Model
if ($LASTEXITCODE -ne 0) {
    throw "ollama pull $Model failed (exit code $LASTEXITCODE)."
}

# ---------------------------------------------------------------------------
Write-Step "Getting the repo at $InstallDir"

if (Test-Path (Join-Path $InstallDir '.git')) {
    Write-Host "    Repo already present; pulling latest instead of cloning."
    git -C $InstallDir pull --ff-only
    if ($LASTEXITCODE -ne 0) { throw "Git update failed. Resolve the checkout problem, then rerun setup." }
} elseif (Test-Path $InstallDir) {
    Write-Warn "$InstallDir exists but is not a git repo. Not touching it -- move it aside or pass a different -InstallDir."
    throw "InstallDir exists and is not a git checkout."
} else {
    git clone $RepoUrl $InstallDir
    if ($LASTEXITCODE -ne 0) { throw "Git clone failed. Check repository access, then rerun setup." }
}

# ---------------------------------------------------------------------------
Write-Step "Installing Python dependencies (uv sync)"
Push-Location $InstallDir
try {
    uv sync --locked --extra dev
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed (exit code $LASTEXITCODE)." }

    if (-not $SkipTests) {
        Write-Step "Running the test suite on this machine"
        uv run pytest -q
        if ($LASTEXITCODE -ne 0) {
            throw "Tests failed. Fix the reported failures before registering the server."
        }
        Write-Host "    All tests passed (including Windows-specific tests)."

    }
} finally {
    Pop-Location
}

# ---------------------------------------------------------------------------
Write-Step "Creating data folders and registering Claude Desktop"

Push-Location $InstallDir
try {
$setupArgs = @('--data-dir', $DataDir, '--model', $Model)
if ($FallbackModel) { $setupArgs += @('--fallback-model', $FallbackModel) }
uv run --locked sap-incident-lab setup @setupArgs --pull-model
    if ($LASTEXITCODE -ne 0) { throw "Application setup failed. See the recovery message above." }

    Write-Step "Checking folders, model, and a synthetic extraction"
    uv run --locked sap-incident-lab doctor
    if ($LASTEXITCODE -ne 0) { throw "Diagnostics failed. Follow the suggested next steps, then rerun doctor." }
} finally {
    Pop-Location
}

Write-Step "Setup verified"
Write-Host @"

Fully quit and reopen Claude Desktop.
For a first investigation, run from ${InstallDir}:
  uv run sap-incident-lab demo
Then ask Claude:
  Investigate INC-DEMO-001 and explain why the import failed.

To add your own selected text exports:
  uv run sap-incident-lab import INC-123 'C:\exports\import.log' 'C:\exports\trace.txt'

See docs/quickstart.md for progress, resume, and reporting.
"@ -ForegroundColor Green
