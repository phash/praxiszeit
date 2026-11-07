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
#      PostgreSQL-Dienst (NetworkService) gehoert und nur ihnen Rechte gibt -
#      festgestellt VOR jedem Eigentuemerwechsel; sonst wird es zurueckgesetzt
#      und bekommt den Dienst-Eintrag neu.
#      Jeder Teilbaum wird zuerst von oben nach unten Ordner fuer Ordner
#      gesperrt (Eigentuemer + geerbte Rechte, ohne /T) und dabei geprueft;
#      erst danach laufen die rekursiven icacls-Aufrufe (/T), wenn kein anderes
#      Konto dort mehr schreiben kann. Ein bin\postgresql, das setup.bat als
#      Verknuepfung auf ein System-PostgreSQL angelegt hat, wird nicht betreten.
#      Jede andere Verknuepfung (Junction, symbolischer Link), jede Datei mit
#      mehreren harten Links und jeder Name mit Leerzeichen oder Punkt am Ende
#      sperrt die Installation (Exit 2) - icacls /T folgt Verknuepfungen, ein
#      harter Link teilt die Rechte mit einer Datei ausserhalb, und Windows
#      PowerShell 5.1 kuerzt solche Namen beim Auflisten.
#   0. Vorab, vor jeder Aenderung: liegen in data\db oder config schon Dateien,
#      die weder einem Administrator, SYSTEM noch dem Datenbankdienst gehoeren,
#      und zeigt kein PraxisZeit-Dienst auf diesen Ordner, sperrt das die
#      Installation (Exit 2). Der Dienst wuerde eine vorab angelegte Datenbank
#      oder Konfiguration (.db-credentials, .secret-key, praxiszeit.conf)
#      sonst uebernehmen.
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

# Anzahl harter Links einer Datei (GetFileInformationByHandle). Nur mit
# FILE_READ_ATTRIBUTES geoeffnet, ohne einer Verknuepfung zu folgen; -1 = nicht
# feststellbar (gilt als Befund). Ohne diese Pruefung keine Installation.
$PzFileLinksCode = @'
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class PzFileLinks {
    [StructLayout(LayoutKind.Sequential)]
    struct Info {
        public uint Attributes;
        public System.Runtime.InteropServices.ComTypes.FILETIME Created, Accessed, Written;
        public uint Volume, SizeHigh, SizeLow, Links, IndexHigh, IndexLow;
    }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern SafeFileHandle CreateFileW(string name, uint access, uint share, IntPtr sa,
        uint disposition, uint flags, IntPtr template);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool GetFileInformationByHandle(SafeFileHandle h, out Info info);
    public static long Count(string path) {
        string p = path.StartsWith(@"\\") ? @"\\?\UNC\" + path.Substring(2) : @"\\?\" + path;
        using (SafeFileHandle h = CreateFileW(p, 0x80, 7, IntPtr.Zero, 3, 0x02200000, IntPtr.Zero)) {
            if (h.IsInvalid) { return -1; }
            Info i;
            if (!GetFileInformationByHandle(h, out i)) { return -1; }
            return i.Links;
        }
    }
}
'@
try {
    Add-Type -Language CSharp -TypeDefinition $PzFileLinksCode -ErrorAction Stop
} catch {
    Write-Output "FEHLER: Die Pruefung auf harte Links liess sich nicht laden - $_"
    exit 1
}

function Test-OddName([string]$Name) {
    # Leerzeichen oder Punkt am Ende: Windows PowerShell 5.1 (.NET Framework)
    # kuerzt das beim Auflisten weg - "a " wuerde als "a" gelistet, sein Inhalt
    # nie geprueft, icacls /T dagegen behielte den Namen.
    return ($Name -match '[ .]$')
}

function Get-TrustedOwnerSids {
    # Wer Eigentuemer einer Datei sein kann, ohne Administrator zu sein, ist
    # nur ihr Ersteller - ein normales Konto kann keine Datei anlegen, die
    # SYSTEM, den Administratoren oder dem Datenbankdienst gehoert.
    $sids = New-Object System.Collections.Generic.List[string]
    foreach ($s in @('S-1-5-18', 'S-1-5-32-544', 'S-1-5-20')) { $sids.Add($s) }
    $sids.Add([System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value)
    try {
        foreach ($m in @(Get-LocalGroupMember -SID 'S-1-5-32-544' -ErrorAction Stop)) {
            if ($m.SID) { $sids.Add($m.SID.Value) }
        }
    } catch { }
    return ,$sids
}

function Get-UntrustedFiles([string]$Dir, [string[]]$SkipTopFiles) {
    # Audit-Runde 5: Dateien unter $Dir, deren Eigentuemer kein Administrator,
    # SYSTEM oder der Datenbankdienst ist - festgestellt VOR jedem
    # /setowner (danach gehoerte alles den Administratoren). Gibt die Pfade
    # aus; Verknuepfung, auffaelliger Name oder nicht lesbarer Eintrag zaehlen
    # mit. Ordner selbst zaehlen nicht (das Paket bringt leere Ordner mit).
    if (-not (Test-Path -LiteralPath $Dir)) { return }
    $trusted = Get-TrustedOwnerSids
    $sidType = [System.Security.Principal.SecurityIdentifier]
    $stack = New-Object System.Collections.Generic.Stack[object]
    try {
        $stack.Push((Get-Item -LiteralPath $Dir -Force -ErrorAction Stop))
    } catch {
        Write-Output "$Dir (nicht lesbar)"
        return
    }
    while ($stack.Count -gt 0) {
        $item = $stack.Pop()
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            Write-Output "$($item.FullName) (Verknuepfung)"
            continue
        }
        if ($item.PSIsContainer) {
            try {
                $children = @(Get-ChildItem -LiteralPath $item.FullName -Force -ErrorAction Stop)
            } catch {
                Write-Output "$($item.FullName) (nicht lesbar)"
                continue
            }
            foreach ($c in $children) {
                if (Test-OddName $c.Name) { Write-Output "$($c.FullName) (Name)"; continue }
                if ($item.FullName -eq $Dir -and -not $c.PSIsContainer -and $SkipTopFiles -contains $c.Name) { continue }
                $stack.Push($c)
            }
            continue
        }
        try {
            $owner = $item.GetAccessControl('Owner').GetOwner($sidType).Value
        } catch {
            Write-Output "$($item.FullName) (nicht lesbar)"
            continue
        }
        if ($trusted -notcontains $owner) { Write-Output "$($item.FullName) (Eigentuemer $owner)" }
    }
}

function Test-InstallEvidence([string]$Root) {
    # Ein PraxisZeit-Dienst, der auf diesen Ordner zeigt, belegt eine fruehere
    # Installation durch einen Administrator (Dienste anlegen kann nur er).
    foreach ($svc in @('PraxisZeit-PostgreSQL', 'PraxisZeit')) {
        try {
            $img = (Get-ItemProperty -LiteralPath "HKLM:\SYSTEM\CurrentControlSet\Services\$svc" -Name ImagePath -ErrorAction Stop).ImagePath
        } catch {
            continue
        }
        if ($img -and $img.Replace('/', '\').IndexOf($Root + '\', [System.StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
    }
    return $false
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
    # auffaelliger Name, nicht lesbarer Eintrag oder Fehler = $false (dann wird
    # zurueckgesetzt). Frueher genuegte eine Datei PG_VERSION - die kann jeder
    # anlegen, der dort schreiben darf. Aufruf VOR jedem /setowner (Runde 5:
    # danach gehoerte alles den Administratoren, die Eigentuemer-Pruefung
    # griffe nie). Nur $true/$false in die Pipeline.
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
                    if (Test-OddName $c.Name) { return $false }
                    $items.Push($c)
                }
            }
        }
    } catch {
        return $false
    }
    return $true
}

function Test-DirLocked([string]$Dir) {
    # Schon gesperrt: Eigentuemer Administratoren, Vererbung aktiv, nur geerbte
    # Eintraege fuer SYSTEM, Administratoren, Benutzer, NetworkService. Dann
    # kann dort kein anderes Konto schreiben - die beiden icacls-Aufrufe je
    # Ordner (bei jedem Update tausende) entfallen. Fehler = nicht gesperrt.
    $sidType = [System.Security.Principal.SecurityIdentifier]
    try {
        $acl = [System.IO.Directory]::GetAccessControl($Dir, [System.Security.AccessControl.AccessControlSections]'Access, Owner')
        if ($acl.GetOwner($sidType).Value -ne 'S-1-5-32-544') { return $false }
        if ($acl.AreAccessRulesProtected) { return $false }
        foreach ($rule in $acl.GetAccessRules($true, $true, $sidType)) {
            if (-not $rule.IsInherited) { return $false }
            if (@('S-1-5-18', 'S-1-5-32-544', 'S-1-5-32-545', 'S-1-5-20') -notcontains $rule.IdentityReference.Value) { return $false }
        }
    } catch {
        return $false
    }
    return $true
}

function Lock-TreeTopDown([string]$Dir) {
    # Audit-Runde 5: erst sperren, dann pruefen, dann rekursiv. Von oben nach
    # unten, Ordner fuer Ordner: Eigentuemer Administratoren und geerbte Rechte
    # fuer DIESEN Ordner (icacls ohne /T), dann seine Eintraege auflisten. Ein
    # Konto mit eigenem Eintrag an einem Unterordner verliert so sein
    # Schreibrecht, BEVOR der Ordner geprueft wird - eine Verknuepfung, die es
    # nach der Pruefung anlegt, ist nicht mehr moeglich, und die rekursiven
    # icacls-Aufrufe danach (/T) laufen ueber einen Baum, in dem nur noch
    # SYSTEM und Administratoren schreiben. Grenze: ein Handle mit
    # Schreibrecht, das vor dem Sperren geoeffnet wurde, bleibt gueltig.
    # Befunde (Exit 2): Verknuepfung (Junction, symbolischer Link; nie
    # betreten), Datei mit mehreren harten Links (icacls aendert die Rechte,
    # die alle Links teilen - auch die einer Datei ausserhalb), Name mit
    # Leerzeichen oder Punkt am Ende. Ein Ordner, der sich nicht auflisten
    # laesst, ist ungeprueft (Exit 1). Iterativ statt Get-ChildItem -Recurse
    # (das folgt unter Windows PowerShell 5.1 Verzeichnis-Verknuepfungen).
    # Aufruf als Anweisung, nie zuweisen: die Meldungen gingen sonst verloren.
    $links = New-Object System.Collections.Generic.List[string]
    $hard = New-Object System.Collections.Generic.List[string]
    $odd = New-Object System.Collections.Generic.List[string]
    $stack = New-Object System.Collections.Generic.Stack[string]
    $stack.Push($Dir)
    while ($stack.Count -gt 0) {
        $d = $stack.Pop()
        if (-not (Test-DirLocked $d)) {
            Invoke-Icacls @($d, '/setowner', $SidAdmins, '/C', '/Q')
            Invoke-Icacls @($d, '/reset', '/C', '/Q')
        }
        try {
            $items = @(Get-ChildItem -LiteralPath $d -Force -ErrorAction Stop)
        } catch {
            Write-Output "FEHLER: $d laesst sich nicht auflisten und damit nicht pruefen - $_"
            exit 1
        }
        foreach ($item in $items) {
            if (Test-OddName $item.Name) { $odd.Add($item.FullName); continue }
            if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                $links.Add($item.FullName)
                continue
            }
            if ($item.PSIsContainer) {
                $stack.Push($item.FullName)
            } elseif ([PzFileLinks]::Count($item.FullName) -ne 1) {
                $hard.Add($item.FullName)
            }
        }
    }
    Write-TreeFindings $Dir $links $hard $odd
}

function Assert-SingleFile([string]$Path) {
    # Einzelne Datei (Wurzel, bin\): Name und harte Links wie Lock-TreeTopDown.
    $none = New-Object System.Collections.Generic.List[string]
    $hard = New-Object System.Collections.Generic.List[string]
    $odd = New-Object System.Collections.Generic.List[string]
    if (Test-OddName (Split-Path -Leaf $Path)) { $odd.Add($Path) }
    elseif ([PzFileLinks]::Count($Path) -ne 1) { $hard.Add($Path) }
    Write-TreeFindings (Split-Path -Parent $Path) $none $hard $odd
}

function Write-TreeFindings([string]$Dir, $Links, $Hard, $Odd) {
    if (($Links.Count + $Hard.Count + $Odd.Count) -eq 0) { return }
    if ($Links.Count -gt 0) {
        Write-Output "FEHLER: Unter $Dir liegen Verknuepfungen (Junction oder symbolischer Link)."
        Write-Output 'Beim Zuruecksetzen der Rechte wuerde ihnen gefolgt und Eigentuemer und Rechte'
        Write-Output 'ausserhalb des Installationsordners geaendert.'
        foreach ($f in ($Links | Select-Object -First 50)) { Write-Output "  $f" }
        if ($Links.Count -gt 50) { Write-Output "  ... und $($Links.Count - 50) weitere" }
    }
    if ($Hard.Count -gt 0) {
        Write-Output "FEHLER: Unter $Dir liegen Dateien mit mehreren harten Links (oder ihre Linkzahl"
        Write-Output 'ist nicht feststellbar). Ihre Rechte teilen sie mit jeder anderen Stelle, an der'
        Write-Output 'sie verlinkt sind - auch ausserhalb des Installationsordners.'
        foreach ($f in ($Hard | Select-Object -First 50)) { Write-Output "  $f" }
        if ($Hard.Count -gt 50) { Write-Output "  ... und $($Hard.Count - 50) weitere" }
    }
    if ($Odd.Count -gt 0) {
        Write-Output "FEHLER: Unter $Dir liegen Eintraege, deren Name mit Leerzeichen oder Punkt endet"
        Write-Output '(Windows zeigt sie unter anderem Namen an, ihr Inhalt laesst sich nicht pruefen).'
        foreach ($f in ($Odd | Select-Object -First 50)) { Write-Output "  $f" }
        if ($Odd.Count -gt 50) { Write-Output "  ... und $($Odd.Count - 50) weitere" }
    }
    Write-Output 'Die Installation ist gesperrt, bis diese Eintraege entfernt sind (oder in einen'
    Write-Output 'neuen, leeren Ordner installieren).'
    exit 2
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

# --- 0. Vorab: Herkunft von data\db und config, VOR jeder Aenderung ---
# Audit-Runde 5: was danach /setowner /T anfasst, gehoert den Administratoren -
# die Herkunft laesst sich nur jetzt noch feststellen.
$dbDir = Join-Path $root 'data\db'
$configDir = Join-Path $root 'config'
$untrusted = @(Get-UntrustedFiles $dbDir @()) + @(Get-UntrustedFiles $configDir @('praxiszeit.conf.example'))
$evidence = Test-InstallEvidence $root
if ($untrusted.Count -gt 0 -and -not $evidence) {
    Write-Output 'FEHLER: In data\db oder config liegen Dateien, deren Herkunft nicht belegt ist -'
    Write-Output 'sie gehoeren weder einem Administrator noch SYSTEM oder dem Datenbankdienst, und'
    Write-Output 'kein PraxisZeit-Dienst ist fuer diesen Ordner eingerichtet. Eine vorab angelegte'
    Write-Output 'Datenbank oder Konfiguration wuerde PraxisZeit sonst uebernehmen. Die Installation'
    Write-Output 'ist gesperrt, bis diese Dateien entfernt sind (oder in einen neuen, leeren Ordner'
    Write-Output 'installieren):'
    foreach ($u in ($untrusted | Select-Object -First 50)) { Write-Output "  $u" }
    if ($untrusted.Count -gt 50) { Write-Output "  ... und $($untrusted.Count - 50) weitere" }
    exit 2
}
# data\db bleibt nur stehen, wenn es samt Inhalt schon nur dem Dienst gehoert -
# geprueft, solange die Eigentuemer noch die alten sind.
$dbServiceOnly = (Test-Path -LiteralPath $dbDir) -and (Test-ServiceOnlyAcl $dbDir)

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
# Jeder Teilbaum: erst Lock-TreeTopDown (Ordner fuer Ordner sperren und
# pruefen), dann die rekursiven icacls-Aufrufe (/T) - siehe dort.
$pgDir = Join-Path $root 'bin\postgresql'
$pgIsLink = Test-ReparsePoint $pgDir
foreach ($entry in Get-ChildItem -LiteralPath $root -Force) {
    $p = $entry.FullName
    if (Test-OddName $entry.Name) { Assert-SingleFile $p }
    if (Test-ReparsePoint $p) {
        # Eine Verknuepfung direkt in der Wurzel (etwa data -> anderer Ordner)
        # legte Datenbank oder Konfiguration ausserhalb des gesicherten Ordners ab.
        Write-Output "FEHLER: $p ist eine Verknuepfung (Junction oder symbolischer Link)."
        Write-Output 'Die Installation ist gesperrt, bis sie entfernt ist (oder in einen neuen, leeren'
        Write-Output 'Ordner installieren).'
        exit 2
    }
    if ($entry.PSIsContainer) {
        if ($entry.Name -eq 'bin') {
            Invoke-Icacls @($p, '/setowner', $SidAdmins, '/C', '/Q')
            Invoke-Icacls @($p, '/reset', '/C', '/Q')
            foreach ($sub in Get-ChildItem -LiteralPath $p -Force) {
                if ($sub.FullName -eq $pgDir -and $pgIsLink) { continue }
                if (Test-OddName $sub.Name) { Assert-SingleFile $sub.FullName }
                if (Test-ReparsePoint $sub.FullName) { continue }
                if ($sub.PSIsContainer) {
                    Lock-TreeTopDown $sub.FullName
                    Invoke-Icacls @($sub.FullName, '/setowner', $SidAdmins, '/T', '/C', '/Q')
                    Invoke-Icacls @($sub.FullName, '/reset', '/T', '/C', '/Q')
                } else {
                    Assert-SingleFile $sub.FullName
                    Invoke-Icacls @($sub.FullName, '/setowner', $SidAdmins, '/C', '/Q')
                    Invoke-Icacls @($sub.FullName, '/reset', '/C', '/Q')
                }
            }
        } elseif ($entry.Name -eq 'app') {
            Lock-TreeTopDown $p
            Invoke-Icacls @($p, '/setowner', $SidAdmins, '/T', '/C', '/Q')
            Invoke-Icacls @($p, '/reset', '/T', '/C', '/Q')
        } else {
            # data, config, logs (und jeder andere Ordner): Eigentuemer und die
            # eigene DACL genau aus der Positivliste fuer den Ordner selbst (wie
            # praxiszeit-server.py harden-permissions danach) - ohne /T, die
            # Inhalte folgen einzeln.
            Invoke-Icacls @($p, '/setowner', $SidAdmins, '/C', '/Q')
            switch ($entry.Name) {
                'data' { Set-ExactDacl $p $SddlData @('S-1-5-18', 'S-1-5-32-544', 'S-1-5-20') }
                'logs' { Set-ExactDacl $p $SddlLogs @('S-1-5-18', 'S-1-5-32-544', 'S-1-5-20') }
                'config' { Set-ExactDacl $p $SddlConfig @('S-1-5-18', 'S-1-5-32-544') }
                default { Invoke-Icacls @($p, '/reset', '/C', '/Q') }
            }
            # Final-Review (S3-01-Rest): Inhalte auf die geerbten Rechte
            # zuruecksetzen. Wer data\backups (oder ein leeres data\db) vor der
            # Installation mit geschuetzter DACL und eigenem Eintrag anlegt,
            # behielte sonst Lesezugriff auf jede naechtliche Sicherung bzw.
            # Schreibzugriff auf postgresql.conf. data\db bleibt nur stehen,
            # wenn es samt Inhalt schon nur dem Dienst gehoert ($dbServiceOnly,
            # festgestellt vor jedem Eigentuemerwechsel - Audit-Runde 5). Sonst
            # wird es zurueckgesetzt und bekommt wieder genau den Eintrag fuer
            # den PostgreSQL-Dienst - NetworkService Vollzugriff (OI)(CI),
            # dieselbe icacls-Zeile wie praxiszeit-server.py
            # _build_icacls_grant_args bei pg_init/pg_start. Vertrauliche
            # Dateien (config\*.conf, key.pem, license.key) haertet setup.bat
            # bzw. der Dienststart danach wieder eigens.
            foreach ($child in Get-ChildItem -LiteralPath $p -Force) {
                if (Test-OddName $child.Name) { Assert-SingleFile $child.FullName }
                if (Test-ReparsePoint $child.FullName) {
                    Write-Output "FEHLER: $($child.FullName) ist eine Verknuepfung (Junction oder symbolischer Link)."
                    Write-Output 'Die Installation ist gesperrt, bis sie entfernt ist (oder in einen neuen, leeren'
                    Write-Output 'Ordner installieren).'
                    exit 2
                }
                $isDb = ($entry.Name -eq 'data' -and $child.Name -eq 'db' -and $child.PSIsContainer)
                if ($isDb -and $dbServiceOnly) { continue }
                if ($child.PSIsContainer) {
                    if ($isDb) { Write-Output "HINWEIS: $($child.FullName) trug Rechte anderer Konten - wird zurueckgesetzt." }
                    Lock-TreeTopDown $child.FullName
                    Invoke-Icacls @($child.FullName, '/setowner', $SidAdmins, '/T', '/C', '/Q')
                    Invoke-Icacls @($child.FullName, '/reset', '/T', '/C', '/Q')
                    if ($isDb) {
                        Invoke-Icacls @($child.FullName, '/grant', "${SidNetworkService}:(OI)(CI)F", '/T', '/C', '/Q')
                    }
                } else {
                    Assert-SingleFile $child.FullName
                    Invoke-Icacls @($child.FullName, '/setowner', $SidAdmins, '/C', '/Q')
                    Invoke-Icacls @($child.FullName, '/reset', '/C', '/Q')
                }
            }
        }
    } else {
        Assert-SingleFile $p
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
