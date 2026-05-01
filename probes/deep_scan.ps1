$reportPath = Join-Path $PSScriptRoot "..\output\reports\system_health_report.txt"
$log = @()

$log += "=== Deep System Health Audit ==="
$log += "Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$log += ""

$log += "## 1. Storage & SMART"
$disks = Get-PhysicalDisk | Select-Object DeviceId, FriendlyName, MediaType, OperationalStatus, HealthStatus, Size
foreach ($d in $disks) {
    if ($d.Size) {
        $sizeGB = [math]::Round($d.Size / 1GB, 1)
        $log += "[$($d.DeviceId)] $($d.FriendlyName) | Type: $($d.MediaType) | Status: $($d.OperationalStatus) | Health: $($d.HealthStatus) | Size: $($sizeGB) GB"
    }
}
$log += ""

$log += "## 2. Windows Core Files (DISM & SFC Context)"
$log += "Running DISM CheckHealth..."
$dism = dism /Online /Cleanup-Image /CheckHealth 2>&1
foreach ($l in $dism) { $log += "  $l" }

$log += ""
$log += "Checking CBS Logs for recent unrepairable SFC errors..."
$cbsPath = "$env:windir\Logs\CBS\CBS.log"
if (Test-Path $cbsPath) {
    $cbsErrors = Select-String -Path $cbsPath -Pattern "Cannot repair member file" -Context 0,0 -Wait:$false | Select-Object -Last 5
    if ($cbsErrors) {
        $log += "Found corrupted system files:"
        foreach ($e in $cbsErrors) { $log += "  $($e.Line)" }
    } else {
        $log += "No recent unrepairable corruptions found in CBS log."
    }
} else {
    $log += "CBS log not found."
}
$log += ""

$log += "## 3. Failed Automatic Services"
$failedServices = Get-WmiObject Win32_Service | Where-Object { $_.StartMode -eq "Auto" -and $_.State -ne "Running" }
if ($failedServices) {
    foreach ($s in $failedServices) {
        $log += "Failed Service: $($s.DisplayName) ($($s.Name)) - State: $($s.State)"
    }
} else {
    $log += "All automatic services are running correctly."
}
$log += ""

$log += "## 4. Driver & Device Conflicts"
$badDevices = Get-WmiObject Win32_PnPEntity | Where-Object { $_.ConfigManagerErrorCode -ne 0 }
if ($badDevices) {
    foreach ($dev in $badDevices) {
         $log += "Bad Device: $($dev.Name) - ErrorCode: $($dev.ConfigManagerErrorCode)"
    }
} else {
    $log += "No devices with warning bangs found."
}

$log += ""
$log += "Checking for high-risk filter drivers (klif, vgk, etc)..."
$filterDrivers = @("klif", "kl1", "klnfilter", "vgc", "vgk", "BEDaisy", "EasyAntiCheat")
foreach ($fd in $filterDrivers) {
    $svc = Get-Service -Name $fd -ErrorAction SilentlyContinue
    if ($svc) {
        $log += "Found high-risk driver loaded: $($svc.Name) (State: $($svc.Status))"
    }
}
$log += ""

$log += "## 5. Application Crash Hotspots (Last 24h)"
try {
    $appCrash = Get-WinEvent -FilterHashtable @{LogName='Application'; Id=1000; StartTime=(Get-Date).AddDays(-1)} -ErrorAction Stop
    $crashApps = @()
    foreach ($c in $appCrash) {
        $appName = $c.Properties[0].Value
        if ($appName) { $crashApps += $appName }
    }
    $crashGroups = $crashApps | Group-Object | Sort-Object Count -Descending | Select-Object -First 5
    if ($crashGroups) {
        foreach ($g in $crashGroups) {
            $log += "$($g.Name) crashed $($g.Count) times"
        }
    } else {
        $log += "No frequent app crashes found."
    }
} catch {
    $log += "Failed to read application crash logs or no entries."
}
$log += ""

# Write Output ASCII out file
$log | Out-File -FilePath $reportPath -Encoding Ascii
Write-Host "Done! Report generated at: $reportPath"
