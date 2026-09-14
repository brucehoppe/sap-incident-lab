# Portable control-flow checks: external programs are stubbed, no installs or real configuration writes.
$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot '../../scripts/setup-windows.ps1'
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('incident-setup-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
$global:Calls = [Collections.Generic.List[string]]::new()
$global:FailAt = ''

function global:git {
    $call = 'git ' + ($args -join ' ')
    $global:Calls.Add($call)
    $global:LASTEXITCODE = if ($global:FailAt -eq 'git' -and $args[0] -ne '--version') { 1 } else { 0 }
    'git test version'
}
function global:ollama {
    $global:Calls.Add('ollama ' + ($args -join ' '))
    $global:LASTEXITCODE = 0
}
function global:uv {
    $call = 'uv ' + ($args -join ' ')
    $global:Calls.Add($call)
    $global:LASTEXITCODE = if ($global:FailAt -eq 'tests' -and $call -match 'pytest') { 1 } else { 0 }
}

try {
    foreach ($scenario in @('git', 'tests', 'success')) {
        $global:Calls.Clear()
        $global:FailAt = $scenario
        $install = Join-Path $testRoot $scenario
        New-Item -ItemType Directory -Path (Join-Path $install '.git') -Force | Out-Null
        $failed = $false
        try {
            & $scriptPath -InstallDir $install -DataDir (Join-Path $testRoot 'data')
        } catch {
            if ($scenario -eq "success") { Write-Host $_.Exception.Message }
            $failed = $true
        }
        if ($scenario -eq 'git') {
            if (-not $failed -or ($global:Calls | Where-Object { $_ -match '^uv ' })) {
                throw 'Git failure did not stop installation.'
            }
        } elseif ($scenario -eq 'tests') {
            if (-not $failed -or ($global:Calls | Where-Object { $_ -match 'sap-incident-lab setup' })) {
                throw 'Failed tests did not prevent Desktop registration.'
            }
        } else {
            if ($failed) { throw 'Successful setup unexpectedly failed.' }
            if (@($global:Calls | Where-Object { $_ -match 'pytest' }).Count -ne 1) {
                throw 'Test suite must run exactly once.'
            }
            if (-not ($global:Calls | Where-Object { $_ -match 'sap-incident-lab doctor' })) {
                throw 'Successful setup did not run diagnostics.'
            }
        }
    }
    Write-Host 'PASS: setup stops on Git/test failures and verifies once before successful completion.'
} finally {
    Remove-Item -LiteralPath $testRoot -Recurse -Force
    Remove-Item Function:git, Function:uv, Function:ollama
}
