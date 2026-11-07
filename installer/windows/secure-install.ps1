param(
    [Parameter(Mandatory = $true)][string]$InstallDir,
    # Nur Rechte/Eigentuemer, ohne Abgleich mit dem Paketinhalt (bestehende
    # Installation VOR dem Kopieren der neuen Dateien, update-wizard.ps1).
    [switch]$SkipManifest
)

# ============================================================
# PraxisZeit: Installationsordner absichern (Audit 2026-11-07 S3-01)
#
# Laeuft VOR dem ersten Start von bin\python\python.exe (setup.bat Schritt 0,
# update-wizard.ps1 nach dem Kopieren) und benutzt nur Windows-Bordmittel
# (icacls, PowerShell). Grund: Unter C:\ duerfen normale Konten Ordner anlegen.
# Wer C:\PraxisZeit vor der Installation anlegt, bleibt Eigentuemer (darf die
# Rechte jederzeit zurueckdrehen) und kann Dateien hineinlegen, die der als
# SYSTEM laufende Dienst ausfuehrt - etwa bin\python\Lib\site-packages\zz.pth
# oder eine DLL neben python.exe.
#
#   1. Wurzel: Eigentuemer Administratoren, SYSTEM/Administratoren Vollzugriff,
#      Benutzer und NetworkService nur Lesen/Ausfuehren, Vererbung von C:\ weg;
#      zuletzt die ganze DACL aus der Positivliste ($SddlRoot) - Eintraege
#      fremder Konten verschwinden, das Ergebnis wird nachgeprueft.
#   2. Eigentuemer Administratoren fuer den ganzen Baum; Programmteile (bin,
#      app, Dateien der Wurzel) auf die geerbten Rechte zuruecksetzen - explizite
#      Eintraege, die jemand an einzelne Dateien gehaengt hat, verschwinden.
#      data, logs, config: eigene DACL aus der Positivliste, Inhalte auf die
#      geerbten Rechte zurueck. data\db bleibt nur unangetastet, wenn es samt
#      Inhalt schon ausschliesslich SYSTEM, Administratoren und dem
#      PostgreSQL-Dienst (NetworkService) gehoert und nur ihnen Rechte gibt;
#      sonst wird es zurueckgesetzt und bekommt den Dienst-Eintrag neu.
#      Ein bin\postgresql, das setup.bat als Verknuepfung auf ein System-
#      PostgreSQL angelegt hat, wird nicht betreten. Jede andere Verknuepfung
#      (Junction, symbolischer Link) in einem Teilbaum, den icacls mit /T
#      bearbeitet, sperrt die Installation (Exit 2) - icacls /T folgt ihnen.
#   3. Abgleich mit bin\payload-manifest.txt (beim Bauen erzeugt): jede Datei
#      unter bin\ und app\, die nicht zum Paket gehoert, sperrt die Installation
#      mit Hinweis (Exit 2). Zwischengespeicherte .pyc in __pycache__, die nicht
#      im Paket stehen, werden geloescht - Python erzeugt sie neu.
#
# Exit 0 = gesichert, 1 = Rechte nicht setzbar, 2 = fremde Dateien oder
# Verknuepfungen gefunden.
# ============================================================

# 'Continue': unter Windows PowerShell 5.1 macht 'Stop' jede stderr-Zeile eines
# nativen Programms (icacls ... 2>&1) zu einer abbrechenden Ausnahme. Fehler
# werden hier ueber $LASTEXITCODE geprueft.
$ErrorActionPreference = 'Continue'
$SidSystem = '*S-1-5-18'
$SidAdmins = '*S-1-5-32-544'
$SidUsers = '*S-1-5-32-545'
$SidAuthUsers = '*S-1-5-11'
$SidEveryone = '*S-1-1-0'
$SidNetworkService = '*S-1-5-20'
# Ganze DACL aus einer Positivliste (Fix-Runde S3-01): /grant:r und /remove:g
# erfassen nur die genannten SIDs - ein expliziter Eintrag fuer irgendein
# anderes Konto (vor der Installation mit "icacls /grant" angelegt) ueberlebte
# sonst und vererbte sich mit /reset auf bin\ und app\. Gleiche Zeichenketten
# wie praxiszeit-server.py (WIN_SDDL_*) und InstallDirGuard.cs.
# 0x1200a9 = Lesen/Ausfuehren, 0x1301bf = Aendern; "P" = keine Vererbung.
$SddlRoot = 'D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;0x1200a9;;;BU)(A;OICI;0x1200a9;;;NS)'
$SddlData = 'D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;;0x1200a9;;;NS)'
$SddlLogs = 'D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;0x1301bf;;;NS)'
$SddlConfig = 'D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)'

function Invoke-Icacls([string[]]$IcaclsArgs, [bool]$Mandatory = $true) {
    $out = & icacls.exe @IcaclsArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        if ($Mandatory) {
            Write-Output "FEHLER: icacls $($IcaclsArgs -join ' ') - Exit $LASTEXITCODE - $out"
            exit 1
        }
    }
}

function Set-ExactDacl([string]$Path, [string]$Sddl, [string[]]$Allowed) {
    # Nur der DACL-Abschnitt wird geschrieben (Eigentuemer setzt icacls).
    # Danach nachpruefen: ein anderer Eintrag oder noch aktive Vererbung = Exit 1.
    try {
        $sec = New-Object System.Security.AccessControl.DirectorySecurity
        $sec.SetSecurityDescriptorSddlForm($Sddl, 'Access')
        [System.IO.Directory]::SetAccessControl($Path, $sec)
        $acl = [System.IO.Directory]::GetAccessControl($Path)
    } catch {
        Write-Output "FEHLER: Rechte von $Path liessen sich nicht setzen - $_"
        exit 1
    }
    if (-not $acl.AreAccessRulesProtected) {
        Write-Output "FEHLER: $Path erbt noch Rechte vom uebergeordneten Ordner."
        exit 1
    }
    $bad = @($acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]) |
        Where-Object { $Allowed -notcontains $_.IdentityReference.Value } |
        ForEach-Object { $_.IdentityReference.Value })
    if ($bad.Count -gt 0) {
        Write-Output "FEHLER: Auf $Path stehen noch Rechte fremder Konten: $($bad -join ', ')"
        exit 1
    }
}

function Test-ReparsePoint([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    $item = Get-Item -LiteralPath $Path -Force
    return (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)
}

function Test-ServiceOnlyAcl([string]$Dir) {
    # Audit-Runde 4: $true nur, wenn $Dir und ALLES darin einem von SYSTEM,
    # Administratoren, NetworkService (PostgreSQL-Dienst) gehoert und
    # ausschliesslich Eintraege fuer diese drei Konten traegt (geerbt oder
    # explizit) - so wie pg_init/pg_start das Datenverzeichnis hinterlassen.
    # Dann hat kein anderes Konto Zugriff, ein Zuruecksetzen waere nur ein
    # Risiko fuer den laufenden Datenbankdienst (Update-Assistent: der Dienst
    # laeuft beim ersten Aufruf noch). Ganzer Baum, nicht nur der Ordner: eine
    # geschuetzte DACL an data\db\postgresql.conf reichte sonst. Verknuepfung,
    # nicht lesbarer Eintrag oder Fehler = $false (dann wird zurueckgesetzt).
    # Frueher genuegte eine Datei PG_VERSION - die kann jeder anlegen, der
    # dort schreiben darf. Nur $true/$false in die Pipeline.
    $okSids = @('S-1-5-18', 'S-1-5-32-544', 'S-1-5-20')
    $sidType = [System.Security.Principal.SecurityIdentifier]
    $sections = [System.Security.AccessControl.AccessControlSections]'Access, Owner'
    try {
        $top = Get-Item -LiteralPath $Dir -Force -ErrorAction Stop
        $items = New-Object System.Collections.Generic.Stack[object]
        $items.Push($top)
        while ($items.Count -gt 0) {
            $item = $items.Pop()
            if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { return $false }
            $acl = $item.GetAccessControl($sections)
            if ($okSids -notcontains $acl.GetOwner($sidType).Value) { return $false }
            foreach ($rule in $acl.GetAccessRules($true, $true, $sidType)) {
                if ($okSids -notcontains $rule.IdentityReference.Value) { return $false }
            }
            if ($item.PSIsContainer) {
                foreach ($c in @(Get-ChildItem -LiteralPath $item.FullName -Force -ErrorAction Stop)) {
                    $items.Push($c)
                }
            }
        }
    } catch {
        return $false
    }
    return $true
}

function Assert-NoReparsePointBelow([string]$Dir) {
    # Audit-Runde 4: "icacls /setowner|/reset /T" folgt Junctions und
    # symbolischen Links unterhalb der ersten Ebene - eine vorab angelegte
    # Junction data\backups\x -> C:\Windows\System32 haette dort Eigentuemer
    # und Rechte umgeschrieben. Deshalb VOR jedem /T den ganzen Teilbaum
    # selbst ablaufen: in jeder Tiefe Attributes -band ReparsePoint pruefen,
    # eine Verknuepfung nie betreten, sondern melden und sperren (Exit 2).
    # Iterativ statt Get-ChildItem -Recurse: das folgt unter Windows
    # PowerShell 5.1 Verzeichnis-Verknuepfungen selbst. Ein Ordner, der sich
    # nicht auflisten laesst, ist ungeprueft und sperrt ebenfalls (Exit 1).
    # Aufruf als Anweisung, nie zuweisen: die Meldungen gehen sonst verloren.
    $found = New-Object System.Collections.Generic.List[string]
    $stack = New-Object System.Collections.Generic.Stack[string]
    $stack.Push($Dir)
    while ($stack.Count -gt 0) {
        $d = $stack.Pop()
        try {
            $items = @(Get-ChildItem -LiteralPath $d -Force -ErrorAction Stop)
        } catch {
            Write-Output "FEHLER: $d laesst sich nicht auflisten und damit nicht auf Verknuepfungen pruefen - $_"
            exit 1
        }
        foreach ($item in $items) {
            if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                $found.Add($item.FullName)
                continue
            }
            if ($item.PSIsContainer) { $stack.Push($item.FullName) }
        }
    }
    if ($found.Count -gt 0) {
        Write-Output "FEHLER: Unter $Dir liegen Verknuepfungen (Junction oder symbolischer Link)."
        Write-Output 'Beim Zuruecksetzen der Rechte wuerde ihnen gefolgt und Eigentuemer und Rechte'
        Write-Output 'ausserhalb des Installationsordners geaendert. Die Installation ist gesperrt,'
        Write-Output 'bis diese Verknuepfungen entfernt sind (oder in einen neuen, leeren Ordner'
        Write-Output 'installieren):'
        foreach ($f in ($found | Select-Object -First 50)) { Write-Output "  $f" }
        if ($found.Count -gt 50) { Write-Output "  ... und $($found.Count - 50) weitere" }
        exit 2
    }
}

try {
    $root = (Resolve-Path -LiteralPath $InstallDir -ErrorAction Stop).ProviderPath.TrimEnd('\')
} catch {
    Write-Output "FEHLER: Installationsordner $InstallDir nicht gefunden."
    exit 1
}
if ([System.IO.Path]::GetPathRoot($root).TrimEnd('\') -eq $root) {
    Write-Output "FEHLER: $root ist ein Laufwerks-Stammverzeichnis - bitte in einen Ordner darin installieren."
    exit 1
}

# --- 1. Wurzel ---
Invoke-Icacls @($root, '/setowner', $SidAdmins)
Invoke-Icacls @($root, '/grant:r', "${SidSystem}:(OI)(CI)F")
Invoke-Icacls @($root, '/grant:r', "${SidAdmins}:(OI)(CI)F")
Invoke-Icacls @($root, '/grant:r', "${SidUsers}:(OI)(CI)RX")
Invoke-Icacls @($root, '/grant:r', "${SidNetworkService}:(OI)(CI)RX")
Invoke-Icacls @($root, '/remove:g', $SidAuthUsers) $false
Invoke-Icacls @($root, '/remove:g', $SidEveryone) $false
Invoke-Icacls @($root, '/inheritance:r')
Set-ExactDacl $root $SddlRoot @('S-1-5-18', 'S-1-5-32-544', 'S-1-5-32-545', 'S-1-5-20')

# --- 2. Eigentuemer + Programmteile ---
$pgDir = Join-Path $root 'bin\postgresql'
$pgIsLink = Test-ReparsePoint $pgDir
foreach ($entry in Get-ChildItem -LiteralPath $root -Force) {
    $p = $entry.FullName
    if (Test-ReparsePoint $p) { continue }
    if ($entry.PSIsContainer) {
        if ($entry.Name -eq 'bin') {
            Invoke-Icacls @($p, '/setowner', $SidAdmins, '/C', '/Q')
            Invoke-Icacls @($p, '/reset', '/C', '/Q')
            foreach ($sub in Get-ChildItem -LiteralPath $p -Force) {
                if ($sub.FullName -eq $pgDir -and $pgIsLink) { continue }
                if (Test-ReparsePoint $sub.FullName) { continue }
                if ($sub.PSIsContainer) {
                    Assert-NoReparsePointBelow $sub.FullName
                    Invoke-Icacls @($sub.FullName, '/setowner', $SidAdmins, '/T', '/C', '/Q')
                    Invoke-Icacls @($sub.FullName, '/reset', '/T', '/C', '/Q')
                } else {
                    Invoke-Icacls @($sub.FullName, '/setowner', $SidAdmins, '/C', '/Q')
                    Invoke-Icacls @($sub.FullName, '/reset', '/C', '/Q')
                }
            }
        } elseif ($entry.Name -eq 'app') {
            Assert-NoReparsePointBelow $p
            Invoke-Icacls @($p, '/setowner', $SidAdmins, '/T', '/C', '/Q')
            Invoke-Icacls @($p, '/reset', '/T', '/C', '/Q')
        } else {
            # data, config, logs: Eigentuemer fuer den Baum, die eigene DACL
            # genau aus der Positivliste (wie praxiszeit-server.py
            # harden-permissions danach); die Inhalte siehe unten. Erst den
            # Teilbaum auf Verknuepfungen pruefen (deckt auch das /reset /T
            # der Inhalte unten ab).
            Assert-NoReparsePointBelow $p
            Invoke-Icacls @($p, '/setowner', $SidAdmins, '/T', '/C', '/Q')
            switch ($entry.Name) {
                'data' { Set-ExactDacl $p $SddlData @('S-1-5-18', 'S-1-5-32-544', 'S-1-5-20') }
                'logs' { Set-ExactDacl $p $SddlLogs @('S-1-5-18', 'S-1-5-32-544', 'S-1-5-20') }
                'config' { Set-ExactDacl $p $SddlConfig @('S-1-5-18', 'S-1-5-32-544') }
            }
            # Final-Review (S3-01-Rest): Inhalte auf die geerbten Rechte
            # zuruecksetzen. Wer data\backups (oder ein leeres data\db) vor der
            # Installation mit geschuetzter DACL und eigenem Eintrag anlegt,
            # behielte sonst Lesezugriff auf jede naechtliche Sicherung bzw.
            # Schreibzugriff auf postgresql.conf. data\db bleibt nur stehen,
            # wenn es samt Inhalt schon nur dem Dienst gehoert
            # (Test-ServiceOnlyAcl; frueher reichte eine Datei PG_VERSION, die
            # jeder mit Schreibrecht anlegen konnte - Audit-Runde 4). Sonst wird
            # es zurueckgesetzt und bekommt wieder genau den Eintrag fuer den
            # PostgreSQL-Dienst - NetworkService Vollzugriff (OI)(CI), dieselbe
            # icacls-Zeile wie praxiszeit-server.py _build_icacls_grant_args
            # bei pg_init/pg_start. Vertrauliche
            # Dateien (config\*.conf, key.pem, license.key) haertet setup.bat
            # bzw. der Dienststart danach wieder eigens.
            if ($entry.Name -in @('data', 'logs', 'config')) {
                foreach ($child in Get-ChildItem -LiteralPath $p -Force) {
                    if (Test-ReparsePoint $child.FullName) { continue }
                    $isDb = ($entry.Name -eq 'data' -and $child.Name -eq 'db' -and $child.PSIsContainer)
                    if ($isDb -and (Test-ServiceOnlyAcl $child.FullName)) { continue }
                    if ($child.PSIsContainer) {
                        if ($isDb) { Write-Output "HINWEIS: $($child.FullName) trug Rechte anderer Konten - wird zurueckgesetzt." }
                        Invoke-Icacls @($child.FullName, '/reset', '/T', '/C', '/Q')
                        if ($isDb) {
                            Invoke-Icacls @($child.FullName, '/grant', "${SidNetworkService}:(OI)(CI)F", '/T', '/C', '/Q')
                        }
                    } else {
                        Invoke-Icacls @($child.FullName, '/reset', '/C', '/Q')
                    }
                }
            }
        }
    } else {
        Invoke-Icacls @($p, '/setowner', $SidAdmins, '/C', '/Q')
        Invoke-Icacls @($p, '/reset', '/C', '/Q')
    }
}

if ($SkipManifest) {
    Write-Output 'Installationsordner abgesichert (Rechte und Eigentuemer).'
    exit 0
}

# --- 3. Abgleich mit dem Paketinhalt ---
$manifestPath = Join-Path $root 'bin\payload-manifest.txt'
if (-not (Test-Path -LiteralPath $manifestPath)) {
    Write-Output "FEHLER: $manifestPath fehlt - das Paket ist unvollstaendig."
    exit 2
}
$expected = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
foreach ($line in [System.IO.File]::ReadAllLines($manifestPath)) {
    $rel = $line.Trim()
    if ($rel) { [void]$expected.Add($rel.Replace('/', '\')) }
}
$unexpected = New-Object System.Collections.Generic.List[string]
foreach ($top in @('bin', 'app')) {
    $base = Join-Path $root $top
    if (-not (Test-Path -LiteralPath $base)) { continue }
    $stack = New-Object System.Collections.Generic.Stack[string]
    $stack.Push($base)
    while ($stack.Count -gt 0) {
        $dir = $stack.Pop()
        foreach ($item in Get-ChildItem -LiteralPath $dir -Force -ErrorAction Stop) {
            $rel = $item.FullName.Substring($root.Length + 1)
            if ($item.PSIsContainer) {
                # bin\postgresql installiert setup.bat beim Kunden (EDB oder
                # Verknuepfung auf ein System-PostgreSQL) - nicht im Paket.
                if ($rel -ieq 'bin\postgresql') { continue }
                if (Test-ReparsePoint $item.FullName) {
                    $unexpected.Add($rel + '\ (Verknuepfung)')
                    continue
                }
                $stack.Push($item.FullName)
                continue
            }
            if ($expected.Contains($rel)) { continue }
            if ($rel -imatch '\\__pycache__\\[^\\]+\.pyc$') {
                Remove-Item -LiteralPath $item.FullName -Force -ErrorAction SilentlyContinue
                if (Test-Path -LiteralPath $item.FullName) { $unexpected.Add($rel) }
                continue
            }
            $unexpected.Add($rel)
        }
    }
}
if ($unexpected.Count -gt 0) {
    Write-Output 'FEHLER: Im Installationsordner liegen Dateien, die nicht zu PraxisZeit gehoeren.'
    Write-Output 'Der Dienst laeuft als SYSTEM und wuerde sie ausfuehren. Die Installation ist'
    Write-Output 'gesperrt, bis diese Dateien entfernt sind (oder in einen neuen, leeren Ordner'
    Write-Output 'installieren):'
    foreach ($u in ($unexpected | Select-Object -First 50)) { Write-Output "  $u" }
    if ($unexpected.Count -gt 50) { Write-Output "  ... und $($unexpected.Count - 50) weitere" }
    exit 2
}
Write-Output 'Installationsordner abgesichert und mit dem Paketinhalt abgeglichen.'
exit 0
