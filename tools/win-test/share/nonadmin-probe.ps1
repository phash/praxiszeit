param(
    [Parameter(Mandatory = $true)][string]$InstallDir,
    [Parameter(Mandatory = $true)][string]$OutFile,
    # Dateiname einer Sicherung in data\backups (ohne Pfad). Das Konto kann den
    # Ordner nicht auflisten; der Name kommt deshalb vom Aufrufer.
    [string]$BackupFile = ''
)

# Test-Harness (NICHT Teil des Pakets): laeuft als frisch angelegtes lokales
# Standardkonto (kein Administrator) und versucht, was ein Angreifer auf dem
# Praxisrechner versuchen wuerde. Erwartet: jedes Schreiben in die
# Programmteile und jedes Lesen privater Daten scheitert. Die Lesekontrolle
# auf main.py muss dagegen gelingen - sonst beweist ein "DENIED" nur, dass
# das Konto gar nichts darf, nicht dass die Rechte stimmen.

$results = @()

function Probe([string]$name, [string]$expect, [scriptblock]$action) {
    try {
        & $action | Out-Null
        $got = 'ALLOWED'
        $detail = ''
    } catch {
        $got = 'DENIED'
        $detail = $_.Exception.GetType().Name
    }
    $verdict = if ($got -eq $expect) { 'OK' } else { 'FAIL' }
    $script:results += "PROBE $verdict $name got=$got expected=$expect $detail"
}

$me = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object System.Security.Principal.WindowsPrincipal($me)).IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
$results += "PROBE_USER=$($me.Name) admin=$isAdmin"

Probe 'read_program_main_py' 'ALLOWED' {
    [System.IO.File]::ReadAllBytes((Join-Path $InstallDir 'app\backend\app\main.py'))
}
Probe 'create_file_in_install_root' 'DENIED' {
    [System.IO.File]::WriteAllText((Join-Path $InstallDir 'probe.txt'), 'x')
}
Probe 'create_file_in_bin' 'DENIED' {
    [System.IO.File]::WriteAllText((Join-Path $InstallDir 'bin\probe.txt'), 'x')
}
Probe 'create_file_in_python_lib' 'DENIED' {
    [System.IO.File]::WriteAllText((Join-Path $InstallDir 'bin\python\Lib\sitecustomize.py'), '# probe')
}
# Oeffnen zum Schreiben ohne zu schreiben: aendert nichts, belegt aber das Recht.
Probe 'open_server_py_for_write' 'DENIED' {
    $fs = [System.IO.File]::Open((Join-Path $InstallDir 'praxiszeit-server.py'), 'Open', 'Write', 'ReadWrite')
    $fs.Close()
}
Probe 'open_app_main_py_for_write' 'DENIED' {
    $fs = [System.IO.File]::Open((Join-Path $InstallDir 'app\backend\app\main.py'), 'Open', 'Write', 'ReadWrite')
    $fs.Close()
}
Probe 'list_data_backups' 'DENIED' {
    Get-ChildItem -LiteralPath (Join-Path $InstallDir 'data\backups') -Force -ErrorAction Stop
}
if ($BackupFile) {
    Probe 'read_backup_file' 'DENIED' {
        [System.IO.File]::ReadAllBytes((Join-Path $InstallDir "data\backups\$BackupFile"))
    }
} else {
    $results += 'PROBE FAIL read_backup_file got=SKIPPED (keine Sicherung vorhanden)'
}
Probe 'read_config_conf' 'DENIED' {
    [System.IO.File]::ReadAllBytes((Join-Path $InstallDir 'config\praxiszeit.conf'))
}
Probe 'list_logs' 'DENIED' {
    Get-ChildItem -LiteralPath (Join-Path $InstallDir 'logs') -Force -ErrorAction Stop
}
Probe 'list_data_db' 'DENIED' {
    Get-ChildItem -LiteralPath (Join-Path $InstallDir 'data\db') -Force -ErrorAction Stop
}

$results | Set-Content -LiteralPath $OutFile -Encoding ascii
