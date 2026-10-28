# LanShare Windows build (PowerShell). No system Python required if bootstrap succeeds.
# Usage: Right-click -> Run with PowerShell
# Or:    powershell -ExecutionPolicy Bypass -File .\Build-LanShare.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$EmbedDir = Join-Path $PSScriptRoot ".tools\python-embed"
$EmbedExe = Join-Path $EmbedDir "python.exe"
$PythonVersion = "3.11.9"
$EmbedZip = "python-$PythonVersion-embed-amd64.zip"
$EmbedUrl = "https://www.python.org/ftp/python/$PythonVersion/$EmbedZip"

function Find-Python {
    foreach ($name in @("python", "py")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            if ($name -eq "py") { return @("py", "-3") }
            return @("python")
        }
    }
    return $null
}

function Ensure-EmbeddedPython {
    if (Test-Path $EmbedExe) { return @($EmbedExe) }

    Write-Host "Downloading portable Python $PythonVersion (one-time, into .tools) ..."
    New-Item -ItemType Directory -Force -Path (Split-Path $EmbedDir) | Out-Null
    $zipPath = Join-Path $env:TEMP $EmbedZip
    Invoke-WebRequest -Uri $EmbedUrl -OutFile $zipPath -UseBasicParsing
    if (Test-Path $EmbedDir) { Remove-Item -Recurse -Force $EmbedDir }
    Expand-Archive -Path $zipPath -DestinationPath $EmbedDir -Force
    Remove-Item $zipPath -Force

    $pth = Get-ChildItem $EmbedDir -Filter "python*._pth" | Select-Object -First 1
    if ($pth) {
        $text = Get-Content $pth.FullName -Raw
        if ($text -notmatch "import site") {
            Add-Content -Path $pth.FullName -Value "`nimport site"
        }
    }

    $getPip = Join-Path $env:TEMP "get-pip.py"
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip -UseBasicParsing
    & $EmbedExe $getPip --no-warn-script-location
    Remove-Item $getPip -Force
    return @($EmbedExe)
}

Write-Host "=== LanShare build ===" -ForegroundColor Cyan

$pyArgs = Find-Python
if (-not $pyArgs) {
    $pyArgs = Ensure-EmbeddedPython
}

$py = $pyArgs[0]
$extra = @()
if ($pyArgs.Count -gt 1) { $extra = $pyArgs[1..($pyArgs.Count - 1)] }

Write-Host "Using: $py $($extra -join ' ')"

& $py @extra -m pip install --upgrade pip
& $py @extra -m pip install -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
& $py @extra -m PyInstaller --noconfirm --clean LanShare.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

Write-Host ""
Write-Host "Done:" -ForegroundColor Green
Write-Host "  dist\LanShare-win32-x64\LanShare.exe"
Write-Host "Copy the whole LanShare-win32-x64 folder to other PCs (no install needed)."
Write-Host ""
Read-Host "Press Enter to close"
