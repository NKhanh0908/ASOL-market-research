[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$DataDir = "data",

    [Parameter(Mandatory = $false)]
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$resolvedDataDir = (Resolve-Path (Join-Path $projectRoot $DataDir)).Path
$pythonExe = "$projectRoot\.venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    $pythonExe = (Get-Command python.exe).Source
}

$url = "http://127.0.0.1:$Port"
Write-Host "Starting Casual Scout Web Server on $url..." -ForegroundColor Cyan

$process = Start-Process `
    -FilePath $pythonExe `
    -ArgumentList "-m casual_scout serve --data-dir ""$resolvedDataDir"" --port $Port" `
    -WorkingDirectory $projectRoot `
    -WindowStyle Hidden `
    -PassThru

Write-Host "Web server started (PID: $($process.Id))." -ForegroundColor Green
Write-Host "Open your browser at: $url" -ForegroundColor Yellow
