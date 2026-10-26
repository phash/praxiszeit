param(
    [Parameter(Mandatory = $true)][string]$InstallDir
)

# Test-Harness (NICHT Teil des Pakets): prueft die Rechte des ganzen
# Installationsordners, wie sie praxiszeit-server.py harden-permissions setzt.
#
#   Programmteile (Ordner selbst, bin, app, praxiszeit-server.py):
#       breite Prinzipale duerfen hoechstens LESEN/AUSFUEHREN - jedes
#       Schreibrecht erlaubt einem lokalen Konto, Code des als SYSTEM
#       laufenden Dienstes auszutauschen.
#   Private Ordner (data, data\backups, logs, config):
#       breite Prinzipale duerfen GAR NICHTS.
#
# SID-basiert, also unabhaengig von der Sprache der Windows-Installation.

$broad = @{
    'S-1-5-32-545' = 'BUILTIN\Users'
    'S-1-5-11'     = 'NT AUTHORITY\Authenticated Users'
    'S-1-1-0'      = 'Everyone'
    'S-1-5-32-546' = 'BUILTIN\Guests'
    'S-1-5-4'      = 'NT AUTHORITY\INTERACTIVE'
}

$writeRights = [System.Security.AccessControl.FileSystemRights]'WriteData, AppendData, WriteExtendedAttributes, WriteAttributes, Delete, DeleteSubdirectoriesAndFiles, ChangePermissions, TakeOwnership'

function Test-Path-Acl([string]$path, [bool]$private) {
    Write-Output "----- $path ($(if ($private) {'privat'} else {'Programm'})) -----"
    if (-not (Test-Path -LiteralPath $path)) {
        Write-Output 'VERDICT: MISSING'
        return
    }
    $acl = Get-Acl -LiteralPath $path
    $bad = @()
    foreach ($ace in $acl.Access) {
        $sid = try {
            $ace.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
        } catch {
            $ace.IdentityReference.Value
        }
        Write-Output "  $sid rights=$($ace.FileSystemRights) type=$($ace.AccessControlType) inherited=$($ace.IsInherited) flags=$($ace.InheritanceFlags)"
        if (-not $broad.ContainsKey($sid) -or $ace.AccessControlType -ne 'Allow') { continue }
        if ($private) {
            $bad += "$sid ($($broad[$sid])) $($ace.FileSystemRights)"
        } elseif (($ace.FileSystemRights -band $writeRights) -ne 0) {
            $bad += "$sid ($($broad[$sid])) $($ace.FileSystemRights)"
        }
    }
    Write-Output "  PROTECTED=$($acl.AreAccessRulesProtected)"
    if ($bad.Count -gt 0) {
        Write-Output ('VERDICT: FAIL - ' + ($bad -join '; '))
    } else {
        Write-Output 'VERDICT: OK'
    }
}

$program = @(
    $InstallDir,
    (Join-Path $InstallDir 'bin'),
    (Join-Path $InstallDir 'bin\python\python.exe'),
    (Join-Path $InstallDir 'bin\postgresql\bin\postgres.exe'),
    (Join-Path $InstallDir 'app\backend\app\main.py'),
    (Join-Path $InstallDir 'praxiszeit-server.py')
)
$private = @(
    (Join-Path $InstallDir 'data'),
    (Join-Path $InstallDir 'data\backups'),
    (Join-Path $InstallDir 'logs'),
    (Join-Path $InstallDir 'config')
)
$newestBackup = Get-ChildItem -LiteralPath (Join-Path $InstallDir 'data\backups') -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($newestBackup) { $private += $newestBackup.FullName }

foreach ($p in $program) { Test-Path-Acl $p $false }
foreach ($p in $private) { Test-Path-Acl $p $true }
