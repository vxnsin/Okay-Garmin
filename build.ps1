<#
.SYNOPSIS
    Builds Okay-Garmin: two executables, and the installer if Inno Setup is present.

.DESCRIPTION
    Replaces the v1 build.bat. Everything runs through uv, so no global Python
    installation is needed. The installer step is skipped when Inno Setup 6 is
    not installed -- GitHub Actions has it, a development machine often does not.

.EXAMPLE
    .\build.ps1
    .\build.ps1 -SkipInstaller
#>

[CmdletBinding()]
param(
    [switch]$SkipInstaller,
    [switch]$KeepWork
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Write-Step($text) {
    Write-Host ''
    Write-Host "==> $text" -ForegroundColor Cyan
}

# Windows PowerShell turns a native command's stderr into an ErrorRecord, which
# $ErrorActionPreference = 'Stop' then treats as fatal -- and uv and PyInstaller
# both write ordinary progress to stderr. Run them with that relaxed and judge
# them by their exit code instead.
function Invoke-Native {
    param(
        [Parameter(Mandatory)][string]$What,
        [Parameter(Mandatory, ValueFromRemainingArguments)][string[]]$Arguments
    )
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $exe = $Arguments[0]
        $rest = @()
        if ($Arguments.Length -gt 1) { $rest = $Arguments[1..($Arguments.Length - 1)] }
        & $exe @rest
        if ($LASTEXITCODE -ne 0) { throw "$What failed (exit $LASTEXITCODE)" }
    }
    finally {
        $ErrorActionPreference = $previous
    }
}

# --- version comes from one place only ---------------------------------------
$versionFile = 'src\okay_garmin\version.py'
$match = Select-String -Path $versionFile -Pattern '__version__\s*=\s*"([^"]+)"'
if (-not $match) { throw "Could not read the version from $versionFile" }
$version = $match.Matches[0].Groups[1].Value
Write-Host "Okay-Garmin $version" -ForegroundColor Green

# --- clean --------------------------------------------------------------------
Write-Step 'Cleaning previous builds'
foreach ($dir in 'build', 'dist') {
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
}

# --- dependencies -------------------------------------------------------------
Write-Step 'Syncing dependencies'
Invoke-Native 'uv sync' uv sync --extra build

# --- application --------------------------------------------------------------
Write-Step 'Building Okay-Garmin.exe'
Invoke-Native 'PyInstaller (app)' uv run pyinstaller --noconfirm --onefile --noconsole `
    --name 'Okay-Garmin' `
    --icon 'assets\icon.ico' `
    --add-data 'web;web' `
    --add-data 'assets\icon.ico;assets' `
    --paths 'src' `
    --collect-data 'vosk' `
    --collect-binaries 'vosk' `
    --hidden-import 'okay_garmin' `
    'entrypoints\app.py'

# --- updater ------------------------------------------------------------------
# Console build on purpose: the updater prints its progress, and that is the
# only feedback the user gets while a silent installer runs.
Write-Step 'Building update.exe'
Invoke-Native 'PyInstaller (updater)' uv run pyinstaller --noconfirm --onefile `
    --name 'update' `
    --icon 'assets\icon.ico' `
    --paths 'src' `
    'entrypoints\updater.py'

# --- installer ----------------------------------------------------------------
if (-not $SkipInstaller) {
    $iscc = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1

    if ($iscc) {
        Write-Step 'Building the installer'
        Invoke-Native 'ISCC' $iscc "/DAppVersion=$version" 'installer\okay-garmin.iss'

        $setup = "dist\installer\Okay-Garmin-Setup-$version.exe"
        $hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()

        # The updater refuses to install anything whose hash is not in here.
        $manifest = [ordered]@{
            version = $version
            setup   = [System.IO.Path]::GetFileName($setup)
            sha256  = $hash
            size    = (Get-Item $setup).Length
        }
        $manifest | ConvertTo-Json | Out-File 'dist\installer\latest.json' -Encoding utf8

        Write-Host "SHA-256: $hash" -ForegroundColor DarkGray
    }
    else {
        Write-Warning 'Inno Setup 6 not found -- skipping the installer.'
        Write-Warning 'Install it from https://jrsoftware.org/isdl.php, or build in CI.'
    }
}

if (-not $KeepWork) {
    if (Test-Path 'build') { Remove-Item 'build' -Recurse -Force }
    Remove-Item '*.spec' -Force -ErrorAction SilentlyContinue
}

Write-Step 'Done'
Get-ChildItem dist -Recurse -File |
    Select-Object @{n = 'File'; e = { $_.FullName.Replace("$PWD\", '') } },
                  @{n = 'MB'; e = { [math]::Round($_.Length / 1MB, 1) } } |
    Format-Table -AutoSize
