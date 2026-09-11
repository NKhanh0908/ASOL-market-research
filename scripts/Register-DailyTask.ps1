[CmdletBinding()]
param(
    [string]$DataDir = "data",
    [string]$Time = "07:00",
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$resolvedDataDir = (Join-Path $projectRoot $DataDir)
$pythonExe = "$projectRoot\.venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    $pythonExe = (Get-Command python.exe).Source
}

$taskName = "ASOL-CasualScout-DailyPipeline"
$startBoundary = (Get-Date).ToString("yyyy-MM-ddT$Time:00")

$batchRunner = "$projectRoot\scripts\Run-PipelineSilent.bat"

# Create logs directory if not exists
$logsDir = Join-Path $resolvedDataDir "logs"
if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
}

# Create helper batch file
$batchContent = @"
@echo off
cd /d "$projectRoot"
"$pythonExe" -m casual_scout collect --data-dir "$resolvedDataDir" >> "$logsDir\daily_task.log" 2>&1
"$pythonExe" -m casual_scout analyze --data-dir "$resolvedDataDir" >> "$logsDir\daily_task.log" 2>&1
"@
Set-Content -Path $batchRunner -Value $batchContent -Encoding UTF8

$taskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>ASOL Casual Scout - Daily Automated Pipeline (Collect + Analyze at $Time)</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>$startBoundary</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
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
    <Hidden>true</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT45M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>cmd.exe</Command>
      <Arguments>/c "$batchRunner"</Arguments>
      <WorkingDirectory>$projectRoot</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

if ($Apply) {
    Write-Host "Registering scheduled task '$taskName' to run daily at $Time..." -ForegroundColor Cyan
    Register-ScheduledTask -TaskName $taskName -Xml $taskXml -Force
    Write-Host "Task '$taskName' registered successfully." -ForegroundColor Green
    Write-Host "Log will be written to: $logsDir\daily_task.log" -ForegroundColor Cyan
} else {
    Write-Host "--- Scheduled Task XML Preview (Run with -Apply to register) ---" -ForegroundColor Yellow
    Write-Output $taskXml
}
