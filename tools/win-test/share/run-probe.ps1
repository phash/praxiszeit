param(
    [Parameter(Mandatory = $true)][string]$InstallDir
)

# Test-Harness (NICHT Teil des Pakets): startet nonadmin-probe.ps1 als lokales
# Standardkonto. Laeuft selbst als Administrator (install.bat). Das Kennwort
# des Probekontos ist zufaellig und lebt nur in diesem Prozess.

$ErrorActionPreference = 'Stop'
$user = 'pzprobe'
$chars = [char[]]'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
$pw = -join (1..20 | ForEach-Object { $chars | Get-Random })
$pw = "$pw!9a"
$secure = ConvertTo-SecureString $pw -AsPlainText -Force

if (Get-LocalUser -Name $user -ErrorAction SilentlyContinue) {
    Set-LocalUser -Name $user -Password $secure
} else {
    New-LocalUser -Name $user -Password $secure -PasswordNeverExpires -AccountNeverExpires | Out-Null
}
# Nur "Benutzer", nie Administratoren - sonst beweist die Probe nichts.
Add-LocalGroupMember -SID 'S-1-5-32-545' -Member $user -ErrorAction SilentlyContinue
$inAdmins = Get-LocalGroupMember -SID 'S-1-5-32-544' | Where-Object { $_.Name -like "*\$user" }
Write-Output "PROBE_ACCOUNT=$user in_administrators=$([bool]$inAdmins)"

$probeScript = 'C:\Users\Public\nonadmin-probe.ps1'
$outFile = 'C:\Users\Public\pzprobe-result.txt'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'nonadmin-probe.ps1') -Destination $probeScript -Force
Remove-Item -LiteralPath $outFile -Force -ErrorAction SilentlyContinue

$backup = Get-ChildItem -LiteralPath (Join-Path $InstallDir 'data\backups') -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
$backupName = if ($backup) { $backup.Name } else { '' }
Write-Output "PROBE_BACKUP_FILE=$backupName"

$cred = New-Object System.Management.Automation.PSCredential(".\$user", $secure)
$procArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $probeScript,
          '-InstallDir', $InstallDir, '-OutFile', $outFile)
if ($backupName) { $procArgs += @('-BackupFile', $backupName) }
try {
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList $procArgs -Credential $cred `
        -WorkingDirectory 'C:\Users\Public' -LoadUserProfile -WindowStyle Hidden -Wait -PassThru
    Write-Output "PROBE_EXIT=$($p.ExitCode)"
} catch {
    Write-Output "PROBE FAIL start_as_standard_user $($_.Exception.Message)"
}
if (Test-Path -LiteralPath $outFile) {
    Get-Content -LiteralPath $outFile
} else {
    Write-Output 'PROBE FAIL no_result_file'
}
