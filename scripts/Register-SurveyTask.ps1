[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$DataDir,

    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
$resolvedDataDir = (Resolve-Path $DataDir).Path
$projectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$pythonExe = "$projectRoot\.venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    $pythonExe = (Get-Command python.exe).Source
}

$taskName = "ASOL-Casual-P1-Survey"
$startBoundary = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddT00:00:00Z")

$taskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>ASOL Casual Scout P1 - Schedule Survey Collector (00/06/12/18 UTC)</Description>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <Repetition>
        <Interval>PT6H</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>$startBoundary</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$pythonExe</Command>
      <Arguments>-m casual_scout survey --data-dir "$resolvedDataDir"</Arguments>
      <WorkingDirectory>$projectRoot</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

if ($Apply) {
    Write-Host "Registering scheduled task '$taskName'..." -ForegroundColor Cyan
    Register-ScheduledTask -TaskName $taskName -Xml $taskXml -Force
    Write-Host "Task '$taskName' registered successfully." -ForegroundColor Green
} else {
    Write-Host "--- Scheduled Task XML Preview (Run with -Apply to register) ---" -ForegroundColor Yellow
    Write-Output $taskXml
}
