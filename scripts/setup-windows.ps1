<#
.SYNOPSIS
    Sets up SAP Incident Lab on a Windows machine: uv, Ollama + qwen3:8b, the
    repo itself, the data directories, and the Claude Desktop registration.

.DESCRIPTION
    Mirrors the manual steps in DESIGN.md sections 10-11. Safe to re-run:
    each step checks what's already there before acting, the repo is pulled
    rather than re-cloned if it exists, and the Desktop config is merged
    (never overwritten) with a timestamped backup taken first.

    Does NOT touch INCIDENT_LAB_ROOT contents, any existing mcpServers
    entries (e.g. sap-notes), or run pytest's windows_only marker for you --
    that's still a manual step worth doing once, called out at the end.

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
    Ollama model tag to pull. Default: qwen3:8b

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
    [string]$Model = 'qwen3:8b',
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
Write-Step "Checking prerequisites (git, python)"

foreach ($cmd in @('git', 'python')) {
    if (-not (Test-CommandExists $cmd)) {
        throw "'$cmd' is not on PATH. Install it first, then re-run this script."
    }
    $version = & $cmd --version
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
    git -C $InstallDir pull
} elseif (Test-Path $InstallDir) {
    Write-Warn "$InstallDir exists but is not a git repo. Not touching it -- move it aside or pass a different -InstallDir."
    throw "InstallDir exists and is not a git checkout."
} else {
    git clone $RepoUrl $InstallDir
}

# ---------------------------------------------------------------------------
Write-Step "Installing Python dependencies (uv sync)"
Push-Location $InstallDir
try {
    uv sync --extra dev
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed (exit code $LASTEXITCODE)." }

    if (-not $SkipTests) {
        Write-Step "Running the test suite on this machine"
        uv run pytest -q
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "Tests failed on this machine -- see output above. Continuing setup anyway, but investigate before trusting real evidence to it."
        } else {
            Write-Host "    All tests passed."
        }

        Write-Step "Running the windows_only test group (junctions, ADS -- Mac can't prove these)"
        uv run pytest -m windows_only -q
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "windows_only tests failed or none exist yet -- see DESIGN.md section 11."
        }
    }
} finally {
    Pop-Location
}

# ---------------------------------------------------------------------------
Write-Step "Creating data directories under $DataDir"

$incidentsDir = Join-Path $DataDir 'incidents'
$outputDir = Join-Path $DataDir 'outputs'
$evalDir = Join-Path $DataDir 'evaluation-private'
foreach ($dir in @($incidentsDir, $outputDir, $evalDir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Write-Host "    $dir"
}

# ---------------------------------------------------------------------------
Write-Step "Registering sap-incident-lab in Claude Desktop"

$configPath = Join-Path $env:APPDATA 'Claude\claude_desktop_config.json'
$configDir = Split-Path $configPath -Parent
if (-not (Test-Path $configDir)) {
    New-Item -ItemType Directory -Force -Path $configDir | Out-Null
}

if (Test-Path $configPath) {
    $backupPath = "$configPath.bak-$(Get-Date -Format 'yyyyMMddHHmmss')"
    Copy-Item $configPath $backupPath
    Write-Host "    Backed up existing config to $backupPath"
    $config = Get-Content $configPath -Raw | ConvertFrom-Json
} else {
    Write-Host "    No existing config found; creating a new one."
    $config = [pscustomobject]@{}
}

if (-not ($config.PSObject.Properties.Name -contains 'mcpServers')) {
    $config | Add-Member -NotePropertyName 'mcpServers' -NotePropertyValue ([pscustomobject]@{})
}

$entry = [pscustomobject]@{
    command = $uvPath
    args    = @('run', '--directory', $InstallDir, 'sap-incident-lab', 'serve')
    env     = [pscustomobject]@{
        INCIDENT_LAB_ROOT   = $incidentsDir
        INCIDENT_LAB_OUTPUT = $outputDir
        INCIDENT_LAB_MODEL  = $Model
    }
}

if ($config.mcpServers.PSObject.Properties.Name -contains 'sap-incident-lab') {
    $config.mcpServers.PSObject.Properties.Remove('sap-incident-lab')
}
$config.mcpServers | Add-Member -NotePropertyName 'sap-incident-lab' -NotePropertyValue $entry

$config | ConvertTo-Json -Depth 20 | Set-Content -Path $configPath -Encoding UTF8
Write-Host "    Wrote $configPath (other mcpServers entries, e.g. sap-notes, are untouched)"

# ---------------------------------------------------------------------------
Write-Step "Done"

Write-Host @"

Next steps:
  1. Fully quit Claude Desktop (not just close the window) and reopen it.
  2. Ask it to call incident_lab_health -- expect Ollama reachable,
     '$Model' installed, and config_valid: true.
  3. Confirm your existing sap-notes tools are still present.
  4. Put an incident's exported log/trace files under:
       $incidentsDir\<INCIDENT_ID>\
     alongside an incident.json manifest -- see DESIGN.md section 7 and the
     README for the exact format.

Before pointing this at a REAL incident's evidence: DESIGN.md section 3
treats real SAP traces as sensitive until you've confirmed the data
classification and that this Desktop environment is the approved one for
it. Everything tested so far has been synthetic.
"@ -ForegroundColor Green
