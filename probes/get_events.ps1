$reportPath = Join-Path $PSScriptRoot "..\output\reports\event_check.txt"
$log = @()

$endTime = [datetime]"2026-04-21 13:53:00"
$startTime = [datetime]"2026-04-21 13:48:00"

$log += "=== System Events (13:48 - 13:53) ==="
$sysEvents = Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=$startTime; EndTime=$endTime} -ErrorAction SilentlyContinue
if ($sysEvents) {
    foreach ($e in $sysEvents) {
        $msg = $e.Message -replace "`n", " " -replace "`r", " "
        $log += "$($e.TimeCreated.ToString('HH:mm:ss')) | $($e.ProviderName) | ID: $($e.Id) | $msg"
    }
} else {
    $log += "No system events found."
}

$log += "`n=== Application Events (13:48 - 13:53) ==="
$appEvents = Get-WinEvent -FilterHashtable @{LogName='Application'; StartTime=$startTime; EndTime=$endTime} -ErrorAction SilentlyContinue
if ($appEvents) {
    foreach ($e in $appEvents) {
        $msg = $e.Message -replace "`n", " " -replace "`r", " "
        $log += "$($e.TimeCreated.ToString('HH:mm:ss')) | $($e.ProviderName) | ID: $($e.Id) | $msg"
    }
} else {
    $log += "No application events found."
}

$log | Out-File -FilePath $reportPath -Encoding UTF8
Write-Host "Events saved to $reportPath"
