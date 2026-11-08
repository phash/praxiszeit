param(
    [Parameter(Mandatory = $true)][string]$SecureInstall,
    [Parameter(Mandatory = $true)][string]$PackageTree
)

# Test-Harness (NICHT Teil des Pakets): Negativ- und Grenzfaelle von
# secure-install.ps1 (Audit 2026-11-07 S3-01) in Wegwerf-Ordnern unter C:\hp.
# Laeuft als Administrator (install.bat) und fasst die echte Installation
# C:\PraxisZeit nicht an. Jede Zeile HP_<FALL>=<ergebnis> ist auswertbar:
#   HP_<FALL>_EXIT          Exit-Code von secure-install.ps1
#   HP_<FALL>_VERDICT       OK oder FEHLER (Erwartung im Kommentar je Fall)
# Fremde Eigentuemer: lokales Standardkonto pzprobe (von run-probe.ps1 angelegt,
# hier notfalls nachgeholt) - icacls /setowner darf ein Administrator.

$ErrorActionPreference = 'Continue'
$base = 'C:\hp'
$victim = 'C:\hp-victim'
$user = 'pzprobe'
$script:fails = 0

if (-not (Get-LocalUser -Name $user -ErrorAction SilentlyContinue)) {
    $chars = [char[]]'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    $pw = (-join (1..20 | ForEach-Object { $chars | Get-Random })) + '!9a'
    New-LocalUser -Name $user -Password (ConvertTo-SecureString $pw -AsPlainText -Force) -PasswordNeverExpires | Out-Null
}
$probeSid = (New-Object System.Security.Principal.NTAccount($user)).Translate([System.Security.Principal.SecurityIdentifier]).Value
Write-Output "HP_PROBE_SID=$probeSid"

function New-Case([string]$Name) {
    $root = Join-Path $base $Name
    if (Test-Path -LiteralPath $root) { cmd /c "rmdir /s /q `"$root`"" | Out-Null }
    New-Item -ItemType Directory -Path $root -Force | Out-Null
    return $root
}

function Invoke-Secure([string]$Root, [switch]$SkipManifest) {
    $a = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $SecureInstall, '-InstallDir', $Root)
    if ($SkipManifest) { $a += '-SkipManifest' }
    $out = & powershell.exe @a 2>&1 | Out-String
    return @{ Exit = $LASTEXITCODE; Out = $out }
}

function Get-Sddl([string]$Path) {
    try { return (Get-Acl -LiteralPath $Path).Sddl } catch { return "ERR:$_" }
}

function Report([string]$Case, $Result, [bool]$Ok, [string]$Detail = '') {
    Write-Output "HP_${Case}_EXIT=$($Result.Exit)"
    if ($Detail) { Write-Output "HP_${Case}_DETAIL=$Detail" }
    if ($Ok) { Write-Output "HP_${Case}_VERDICT=OK" } else {
        $script:fails++
        Write-Output "HP_${Case}_VERDICT=FEHLER"
        foreach ($l in ($Result.Out -split "`r?`n" | Where-Object { $_ } | Select-Object -First 12)) {
            Write-Output "  | $l"
        }
    }
}

function Reset-Victim {
    if (Test-Path -LiteralPath $victim) { cmd /c "rmdir /s /q `"$victim`"" | Out-Null }
    New-Item -ItemType Directory -Path "$victim\sub" -Force | Out-Null
    Set-Content -LiteralPath "$victim\file.txt" -Value 'victim'
    # Eigener, auffaelliger Eintrag: ein Zuruecksetzen ueber eine Verknuepfung
    # wuerde ihn entfernen bzw. den Eigentuemer aendern.
    icacls $victim /setowner "*$probeSid" /T /C /Q | Out-Null
    icacls $victim /grant "*${probeSid}:(OI)(CI)M" /T /C /Q | Out-Null
}

function Victim-State { return (Get-Sddl $victim) + '|' + (Get-Sddl "$victim\sub") + '|' + (Get-Sddl "$victim\file.txt") }

# ---------------------------------------------------------------------
# A: data\db mit fremdem Eigentuemer, kein Dienst zeigt auf den Ordner
#    Erwartung: Exit 2, Meldung "Herkunft nicht belegt", data\db unveraendert
#    (Eigentuemer weiter pzprobe, nicht verschoben, nicht geloescht).
# ---------------------------------------------------------------------
$r = New-Case 'A'
New-Item -ItemType Directory -Path "$r\data\db" -Force | Out-Null
Set-Content -LiteralPath "$r\data\db\PG_VERSION" -Value '18'
icacls "$r\data\db" /setowner "*$probeSid" /T /C /Q | Out-Null
$res = Invoke-Secure $r
$owner = (Get-Acl -LiteralPath "$r\data\db\PG_VERSION").GetOwner([System.Security.Principal.SecurityIdentifier]).Value
Report 'A_FREMDES_DB' $res (($res.Exit -eq 2) -and ($res.Out -match 'Herkunft nicht belegt') -and ($owner -eq $probeSid) -and (Test-Path "$r\data\db\PG_VERSION")) "owner_nachher=$owner"

# ---------------------------------------------------------------------
# B: config\.secret-key mit fremdem Eigentuemer, kein Dienst
#    Erwartung: Exit 2 (vorab angelegte Konfiguration wird nicht uebernommen).
# ---------------------------------------------------------------------
$r = New-Case 'B'
New-Item -ItemType Directory -Path "$r\config" -Force | Out-Null
Set-Content -LiteralPath "$r\config\.secret-key" -Value 'aaaa'
icacls "$r\config\.secret-key" /setowner "*$probeSid" /C /Q | Out-Null
$res = Invoke-Secure $r
Report 'B_FREMDE_CONFIG' $res (($res.Exit -eq 2) -and ($res.Out -match 'Herkunft nicht belegt'))

# ---------------------------------------------------------------------
# C: data\db gehoert Administratoren, traegt aber Benutzer:(M)
#    Erwartung: Exit 0 (-SkipManifest), HINWEIS-Zeile, danach kein
#    Benutzer-Eintrag mehr, NetworkService Vollzugriff.
# ---------------------------------------------------------------------
$r = New-Case 'C'
New-Item -ItemType Directory -Path "$r\data\db" -Force | Out-Null
Set-Content -LiteralPath "$r\data\db\PG_VERSION" -Value '18'
icacls "$r\data\db" /grant '*S-1-5-32-545:(OI)(CI)M' /T /C /Q | Out-Null
$res = Invoke-Secure $r -SkipManifest
$sddl = Get-Sddl "$r\data\db"
$fileSddl = Get-Sddl "$r\data\db\PG_VERSION"
$hasNs = ($sddl -match ';FA;;;NS\)')
Report 'C_DB_BENUTZERRECHT' $res (($res.Exit -eq 0) -and ($res.Out -match 'HINWEIS: .*trug Rechte anderer Konten') -and $hasNs -and ($sddl -notmatch '\(A;[^)]*;[^)]*;;;BU\)') -and ($fileSddl -notmatch '\(A;[^)]*;[^)]*;;;BU\)')) "db=$sddl"

# ---------------------------------------------------------------------
# D: data\db sonst nur Dienst (SYSTEM/Admins/NS), aber postgresql.conf mit
#    geschuetzter DACL + Benutzer:F
#    Erwartung: Exit 0, HINWEIS, postgresql.conf danach ohne Benutzer-Eintrag.
# ---------------------------------------------------------------------
$r = New-Case 'D'
New-Item -ItemType Directory -Path "$r\data\db" -Force | Out-Null
Set-Content -LiteralPath "$r\data\db\PG_VERSION" -Value '18'
Set-Content -LiteralPath "$r\data\db\postgresql.conf" -Value 'port = 5432'
icacls "$r\data\db" /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-20:(OI)(CI)F' /C /Q | Out-Null
icacls "$r\data\db\PG_VERSION" /reset /C /Q | Out-Null
icacls "$r\data\db\postgresql.conf" /inheritance:r /grant:r '*S-1-5-18:F' '*S-1-5-32-544:F' '*S-1-5-32-545:F' /C /Q | Out-Null
$res = Invoke-Secure $r -SkipManifest
$conf = Get-Sddl "$r\data\db\postgresql.conf"
Report 'D_PGCONF_GESCHUETZT' $res (($res.Exit -eq 0) -and ($res.Out -match 'HINWEIS') -and ($conf -notmatch '\(A;[^)]*;[^)]*;;;BU\)')) "conf=$conf"

# ---------------------------------------------------------------------
# D2 (Gegenprobe): data\db samt Inhalt nur Dienst -> bleibt unangetastet.
#    Erwartung: Exit 0, KEIN HINWEIS, DACL von data\db unveraendert.
# ---------------------------------------------------------------------
$r = New-Case 'D2'
New-Item -ItemType Directory -Path "$r\data\db" -Force | Out-Null
Set-Content -LiteralPath "$r\data\db\PG_VERSION" -Value '18'
icacls "$r\data\db" /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-20:(OI)(CI)F' /C /Q | Out-Null
icacls "$r\data\db\PG_VERSION" /reset /C /Q | Out-Null
$before = Get-Sddl "$r\data\db"
$res = Invoke-Secure $r -SkipManifest
$after = Get-Sddl "$r\data\db"
Report 'D2_DB_NUR_DIENST' $res (($res.Exit -eq 0) -and ($res.Out -notmatch 'HINWEIS') -and ($before -eq $after))

# ---------------------------------------------------------------------
# E: Junctions in Tiefe >= 2 unter data, app, bin, logs; symbolischer Link
#    (mklink /D). Erwartung je Fall: Exit 2, Rechte/Eigentuemer des Ziels
#    ausserhalb (C:\hp-victim) unveraendert.
# ---------------------------------------------------------------------
$junctionCases = [ordered]@{
    'E1_JUNCTION_DATA' = 'data\backups\tief\j'
    'E2_JUNCTION_APP'  = 'app\backend\x\j'
    'E3_JUNCTION_BIN'  = 'bin\python\Lib\j'
    'E4_JUNCTION_LOGS' = 'logs\alt\j'
}
foreach ($case in $junctionCases.Keys) {
    Reset-Victim
    $r = New-Case $case
    $link = Join-Path $r $junctionCases[$case]
    New-Item -ItemType Directory -Path (Split-Path -Parent $link) -Force | Out-Null
    New-Item -ItemType Junction -Path $link -Target "$victim\sub" | Out-Null
    $vb = Victim-State
    $res = Invoke-Secure $r -SkipManifest
    $va = Victim-State
    Report $case $res (($res.Exit -eq 2) -and ($res.Out -match 'Verknuepfung') -and ($vb -eq $va)) "victim_unveraendert=$($vb -eq $va)"
}
Reset-Victim
$r = New-Case 'E5_SYMLINK_D'
New-Item -ItemType Directory -Path "$r\data\backups\tief" -Force | Out-Null
cmd /c "mklink /D `"$r\data\backups\tief\s`" `"$victim\sub`"" | Out-Null
$vb = Victim-State
$res = Invoke-Secure $r -SkipManifest
$va = Victim-State
Report 'E5_SYMLINK_D' $res (($res.Exit -eq 2) -and ($vb -eq $va)) "victim_unveraendert=$($vb -eq $va)"

# ---------------------------------------------------------------------
# F: harter Link unter data\backups und unter app auf eine Datei ausserhalb
#    Erwartung: Exit 2, Rechte der Zieldatei unveraendert.
# ---------------------------------------------------------------------
foreach ($pair in @(@('F1_HARDLINK_DATA', 'data\backups\h.txt'), @('F2_HARDLINK_APP', 'app\backend\h.py'))) {
    Reset-Victim
    $r = New-Case $pair[0]
    $link = Join-Path $r $pair[1]
    New-Item -ItemType Directory -Path (Split-Path -Parent $link) -Force | Out-Null
    New-Item -ItemType HardLink -Path $link -Target "$victim\file.txt" | Out-Null
    $vb = Victim-State
    $res = Invoke-Secure $r -SkipManifest
    $va = Victim-State
    Report $pair[0] $res (($res.Exit -eq 2) -and ($res.Out -match 'harten Links') -and ($vb -eq $va)) "victim_unveraendert=$($vb -eq $va)"
}

# ---------------------------------------------------------------------
# G: Namen mit Punkt bzw. Leerzeichen am Ende (nur ueber \\?\ anlegbar)
#    Erwartung: Exit 2, Meldung "Leerzeichen oder Punkt".
# ---------------------------------------------------------------------
foreach ($pair in @(@('G1_NAME_PUNKT', 'data\backups\boese.'), @('G2_NAME_LEER', 'app\boese '), @('G3_WURZEL_PUNKT', 'boese.'))) {
    $r = New-Case $pair[0]
    $full = Join-Path $r $pair[1]
    New-Item -ItemType Directory -Path (Split-Path -Parent $full) -Force | Out-Null
    [System.IO.File]::WriteAllText('\\?\' + $full, 'x')
    $res = Invoke-Secure $r -SkipManifest
    Report $pair[0] $res (($res.Exit -eq 2) -and ($res.Out -match 'Leerzeichen oder Punkt'))
}

# ---------------------------------------------------------------------
# H: Ordner mit leerer, geschuetzter DACL und fremdem Eigentuemer unter app
#    Erwartung laut Skript: wird gesperrt (Eigentuemer + /reset) und ist danach
#    auflistbar -> Exit 0; Exit 1 nur, wenn das Auflisten scheitert. Kein
#    Absturz, keine Verknuepfung betreten.
# ---------------------------------------------------------------------
$r = New-Case 'H'
New-Item -ItemType Directory -Path "$r\app\zu\innen" -Force | Out-Null
icacls "$r\app\zu" /setowner "*$probeSid" /T /C /Q | Out-Null
icacls "$r\app\zu" /inheritance:r /C /Q | Out-Null
icacls "$r\app\zu" /remove:g '*S-1-5-18' '*S-1-5-32-544' '*S-1-5-32-545' '*S-1-3-0' '*S-1-5-11' /C /Q | Out-Null
$res = Invoke-Secure $r -SkipManifest
$zu = Get-Sddl "$r\app\zu"
Report 'H_UNLESBARER_ORDNER' $res (($res.Exit -eq 0) -or ($res.Exit -eq 1)) "zu_nachher=$zu"

# ---------------------------------------------------------------------
# I: bin\postgresql schon vorhanden, kein PraxisZeit-Dienst fuer den Ordner
#    (Release-Review 1.23.0 HIGH): setup.bat legt bin\postgresql erst NACH
#    secure-install.ps1 an. I1 = Junction auf fremdes Ziel, I2 = echter Ordner
#    mit pg_ctl.exe. Erwartung: Exit 2, Ziel unveraendert.
# ---------------------------------------------------------------------
Reset-Victim
$r = New-Case 'I1'
New-Item -ItemType Directory -Path "$r\bin\python" -Force | Out-Null
Set-Content -LiteralPath "$r\bin\python\python.exe" -Value 'x'
New-Item -ItemType Junction -Path "$r\bin\postgresql" -Target $victim | Out-Null
$vb = Victim-State
$res = Invoke-Secure $r -SkipManifest
$va = Victim-State
Report 'I1_PG_JUNCTION_VORAB' $res (($res.Exit -eq 2) -and ($res.Out -match 'bin\\postgresql ist schon vorhanden') -and ($vb -eq $va)) "victim_unveraendert=$($vb -eq $va)"
$r = New-Case 'I2'
New-Item -ItemType Directory -Path "$r\bin\postgresql\bin" -Force | Out-Null
Set-Content -LiteralPath "$r\bin\postgresql\bin\pg_ctl.exe" -Value 'x'
$res = Invoke-Secure $r -SkipManifest
Report 'I2_PG_ORDNER_VORAB' $res (($res.Exit -eq 2) -and ($res.Out -match 'bin\\postgresql ist schon vorhanden'))
# I3/I4: Junction mit nicht vorhandenem Ziel (Test-Path folgt ihr und meldet
#    "fehlt") - als bin\postgresql und als data\db. Erwartung: Exit 2.
$r = New-Case 'I3'
New-Item -ItemType Directory -Path "$r\bin" -Force | Out-Null
New-Item -ItemType Directory -Path "$base\gone3" -Force | Out-Null
New-Item -ItemType Junction -Path "$r\bin\postgresql" -Target "$base\gone3" | Out-Null
Remove-Item -LiteralPath "$base\gone3" -Force
$res = Invoke-Secure $r -SkipManifest
Report 'I3_PG_JUNCTION_TOT' $res (($res.Exit -eq 2) -and ($res.Out -match 'bin\\postgresql ist schon vorhanden'))
$r = New-Case 'I4'
New-Item -ItemType Directory -Path "$r\data" -Force | Out-Null
New-Item -ItemType Directory -Path "$base\gone4" -Force | Out-Null
New-Item -ItemType Junction -Path "$r\data\db" -Target "$base\gone4" | Out-Null
Remove-Item -LiteralPath "$base\gone4" -Force
$res = Invoke-Secure $r -SkipManifest
Report 'I4_DB_JUNCTION_TOT' $res ($res.Exit -eq 2)

# ---------------------------------------------------------------------
# J: echtes setup.bat aus dem Paket mit Junction unter data\backups
#    Erwartung: setup.bat bricht bei :fremde_dateien ab ("Setup gesperrt"),
#    Exit 1, Ziel unveraendert, kein Python gestartet (keine conf erzeugt).
# ---------------------------------------------------------------------
Reset-Victim
$r = New-Case 'J'
robocopy $PackageTree $r /E /NFL /NDL /NJH /NJS /NP | Out-Null
New-Item -ItemType Directory -Path "$r\data\backups" -Force | Out-Null
New-Item -ItemType Junction -Path "$r\data\backups\j" -Target "$victim\sub" | Out-Null
$vb = Victim-State
$env:PRAXISZEIT_NONINTERACTIVE = '1'
$out = cmd /c "`"$r\setup.bat`" 2>&1" | Out-String
$setupExit = $LASTEXITCODE
$va = Victim-State
$res = @{ Exit = $setupExit; Out = $out }
Report 'J_SETUP_BAT_JUNCTION' $res (($setupExit -eq 1) -and ($out -match 'Setup gesperrt') -and ($vb -eq $va) -and -not (Test-Path "$r\data\db\PG_VERSION")) "victim_unveraendert=$($vb -eq $va)"

# ---------------------------------------------------------------------
# K: Gegenprobe Paket ohne Befund: secure-install.ps1 mit Manifest gegen
#    eine frische Paketkopie -> Exit 0.
# ---------------------------------------------------------------------
$r = New-Case 'K'
robocopy $PackageTree $r /E /NFL /NDL /NJH /NJS /NP | Out-Null
$res = Invoke-Secure $r
Report 'K_SAUBERES_PAKET' $res ($res.Exit -eq 0)

# ---------------------------------------------------------------------
# L: Paket + fremde Datei unter app (nicht im Manifest) -> Exit 2
# ---------------------------------------------------------------------
$r = New-Case 'L'
robocopy $PackageTree $r /E /NFL /NDL /NJH /NJS /NP | Out-Null
Set-Content -LiteralPath "$r\app\backend\zz_fremd.py" -Value 'print(1)'
$res = Invoke-Secure $r
Report 'L_FREMDE_DATEI_APP' $res ($res.Exit -eq 2)

Write-Output "HP_FAILS=$($script:fails)"
cmd /c "rmdir /s /q `"$base`"" | Out-Null
cmd /c "rmdir /s /q `"$victim`"" | Out-Null
