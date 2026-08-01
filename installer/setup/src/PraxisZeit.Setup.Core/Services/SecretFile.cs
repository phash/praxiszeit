using System.Runtime.Versioning;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;

namespace PraxisZeit.Setup.Core.Services;

/// <summary>
/// Schreibt Dateien mit vertraulichem Inhalt (Admin-Passwort, Signatur-
/// schluessel, privater TLS-Key) so, dass die Zugriffsrechte BEREITS BEIM
/// ANLEGEN eingeschraenkt sind — nicht erst hinterher.
///
/// <para>
/// <strong>Warum die Reihenfolge zaehlt:</strong> wird die Datei zuerst mit
/// Standardrechten angelegt und erst danach eingeschraenkt, existiert ein
/// Zeitfenster, in dem der Klartext fuer jeden lokalen Benutzer lesbar ist.
/// Auf einem Praxis-PC mit mehreren Windows-Konten (Empfang, Aerztin,
/// Vertretung) reicht das aus, um das Admin-Passwort der Zeiterfassung oder
/// den privaten TLS-Schluessel abzugreifen. Unter Linux/macOS schliessen die
/// Shell-Installer dieses Fenster per <c>umask 077</c>; hier ist das
/// Aequivalent fuer den plattformuebergreifenden GUI-Installer.
/// </para>
///
/// <para>
/// <strong>Windows:</strong> die Datei wird mit einem expliziten
/// Security-Descriptor erzeugt (<c>FileInfo.Create(..., FileSecurity)</c>).
/// Der Descriptor wird vom Kernel schon beim <c>CreateFile</c> gesetzt — es
/// gibt also keinen Moment, in dem die Datei die (weiten) Rechte von
/// <c>C:\</c> erbt. Die Vererbung ist abgeschaltet, berechtigt sind nur
/// <c>NT AUTHORITY\SYSTEM</c> und <c>BUILTIN\Administratoren</c>.
/// SYSTEM ist zugleich das Dienstkonto: der PraxisZeit-Dienst wird von
/// <c>install-service.bat</c> ueber NSSM ohne <c>ObjectName</c> registriert
/// und laeuft damit als LocalSystem. <c>Users</c> /
/// <c>Authentifizierte Benutzer</c> / <c>Jeder</c> bekommen kein Recht.
/// Adressiert wird ueber wohlbekannte SIDs, nicht ueber lokalisierte
/// Gruppennamen (deutsches vs. englisches Windows).
/// </para>
///
/// <para>
/// <strong>Linux/macOS:</strong> <c>FileStreamOptions.UnixCreateMode</c>
/// uebergibt den Modus an den <c>open(2)</c>-Aufruf — die Datei entsteht
/// direkt mit 0600.
/// </para>
/// </summary>
public static class SecretFile
{
    private const UnixFileMode OwnerReadWrite = UnixFileMode.UserRead | UnixFileMode.UserWrite;

    /// <summary>
    /// Legt <paramref name="path"/> an (bzw. leert eine vorhandene Datei) und
    /// gibt einen Schreib-Stream zurueck. Die Rechte sind gesetzt, BEVOR der
    /// Aufrufer den ersten Byte schreibt.
    /// </summary>
    public static FileStream Create(string path)
    {
        var dir = Path.GetDirectoryName(path);
        if (!string.IsNullOrEmpty(dir))
        {
            Directory.CreateDirectory(dir);
        }

        // Eine bereits vorhandene Datei behaelt ihren Security-Descriptor —
        // CreateFile ignoriert lpSecurityAttributes fuer existierende Files
        // (Windows) und open(2) den Mode (Unix). Deshalb VOR dem Ueberschreiben
        // haerten, sonst landet der neue Klartext in einer Datei mit den alten,
        // zu weiten Rechten.
        if (File.Exists(path))
        {
            EnsureRestricted(path);
        }

        if (OperatingSystem.IsWindows())
        {
            return CreateWindows(path);
        }

        return new FileStream(path, new FileStreamOptions
        {
            Mode = FileMode.Create,
            Access = FileAccess.Write,
            Share = FileShare.None,
            UnixCreateMode = OwnerReadWrite,
        });
    }

    /// <summary>
    /// Schreibt <paramref name="content"/> nach <paramref name="path"/> mit
    /// von Anfang an eingeschraenkten Rechten.
    /// </summary>
    public static async Task WriteAllTextAsync(
        string path,
        string content,
        Encoding encoding,
        CancellationToken ct = default)
    {
        await using var fs = Create(path);
        var bytes = encoding.GetBytes(content);
        await fs.WriteAsync(bytes, ct).ConfigureAwait(false);
    }

    /// <summary>Synchrone Variante von <see cref="WriteAllTextAsync"/>.</summary>
    public static void WriteAllText(string path, string content, Encoding encoding)
    {
        using var fs = Create(path);
        var bytes = encoding.GetBytes(content);
        fs.Write(bytes, 0, bytes.Length);
    }

    /// <summary>
    /// Korrigiert die Rechte einer BEREITS VORHANDENEN Datei (Bestands-
    /// installation, die noch mit den alten, zu weiten Rechten angelegt
    /// wurde). Idempotent und best-effort: schlaegt der Zugriff auf die ACL
    /// fehl (fehlende Berechtigung, Datei gerade in Benutzung), wird das
    /// bewusst geschluckt — ein Update darf daran nicht scheitern.
    /// </summary>
    public static void EnsureRestricted(string path)
    {
        if (!File.Exists(path))
        {
            return;
        }
        try
        {
            if (OperatingSystem.IsWindows())
            {
                RestrictWindows(path);
            }
            else
            {
                File.SetUnixFileMode(path, OwnerReadWrite);
            }
        }
        catch (Exception ex) when (ex is UnauthorizedAccessException or IOException
                                       or PlatformNotSupportedException or NotSupportedException)
        {
            // Best-effort — siehe Doc-Kommentar.
        }
    }

    [SupportedOSPlatform("windows")]
    private static FileStream CreateWindows(string path)
    {
        return new FileInfo(path).Create(
            FileMode.Create,
            FileSystemRights.WriteData | FileSystemRights.AppendData,
            FileShare.None,
            bufferSize: 4096,
            FileOptions.None,
            BuildRestrictedSecurity());
    }

    [SupportedOSPlatform("windows")]
    private static void RestrictWindows(string path)
    {
        // Ein frisch gebautes FileSecurity-Objekt markiert nur die DACL als
        // geaendert -> SetAccessControl ersetzt genau diese und laesst Owner /
        // SACL unberuehrt. Ergebnis: exakt die beiden Eintraege unten, ohne
        // geerbte "Users"-/"Authentifizierte Benutzer"-Rechte.
        new FileInfo(path).SetAccessControl(BuildRestrictedSecurity());
    }

    [SupportedOSPlatform("windows")]
    private static FileSecurity BuildRestrictedSecurity()
    {
        var security = new FileSecurity();
        // isProtected: true  -> Vererbung von C:\ bzw. dem Installationsordner aus
        // preserveInheritance: false -> die geerbten Eintraege werden NICHT als
        // explizite Kopien uebernommen (sonst bliebe "Users" bestehen).
        security.SetAccessRuleProtection(isProtected: true, preserveInheritance: false);

        // SYSTEM = Dienstkonto (NSSM registriert PraxisZeit als LocalSystem).
        var system = new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null);
        // Lokale Administratorengruppe: damit ein Admin die Konfiguration
        // pflegen und Support-Kommandos ausfuehren kann.
        var administrators = new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid, null);

        security.AddAccessRule(new FileSystemAccessRule(
            system, FileSystemRights.FullControl, AccessControlType.Allow));
        security.AddAccessRule(new FileSystemAccessRule(
            administrators, FileSystemRights.FullControl, AccessControlType.Allow));
        return security;
    }
}
