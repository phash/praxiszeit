namespace PraxisZeit.Setup.Core.Services;

/// <summary>
/// Schutz des Installationsordners einer Neuinstallation (Audit 2026-11-07
/// S3-01). Unter Windows duerfen normale Konten unter <c>C:\</c> Ordner
/// anlegen. Legt ein Praxiskonto <c>C:\PraxisZeit</c> vor der Installation an
/// (oder Dateien wie <c>bin\python\Lib\site-packages\zz.pth</c> hinein), bleibt
/// es Eigentuemer und kann sich jederzeit wieder Vollzugriff geben - der Dienst
/// laeuft als SYSTEM. Deshalb:
/// <list type="bullet">
/// <item>Neuinstallation nur in einen neuen oder leeren Ordner
/// (<see cref="FreshTargetProblem"/>, Hinweis im Assistenten).</item>
/// <item>Der Ordner wird VOR dem Kopieren gehaertet
/// (<see cref="RootHardeningCommands"/>): Eigentuemer Administratoren, nur
/// SYSTEM/Administratoren schreiben, Vererbung von <c>C:\</c> gekappt - in
/// den Sekunden zwischen Kopieren und setup.bat kann niemand Dateien tauschen.</item>
/// </list>
/// </summary>
public static class InstallDirGuard
{
    private const string SidSystem = "*S-1-5-18";
    private const string SidAdministrators = "*S-1-5-32-544";
    private const string SidUsers = "*S-1-5-32-545";
    private const string SidAuthenticatedUsers = "*S-1-5-11";
    private const string SidEveryone = "*S-1-1-0";
    private const string SidNetworkService = "*S-1-5-20";

    /// <summary>
    /// Grund, warum <paramref name="path"/> fuer eine Neuinstallation gesperrt
    /// ist, sonst <c>null</c>.
    /// </summary>
    public static string? FreshTargetProblem(string path)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            return "Bitte einen Installationspfad wählen.";
        }

        string full;
        try
        {
            full = Path.GetFullPath(path);
        }
        catch (Exception)
        {
            return "Der Installationspfad ist ungültig.";
        }

        if (string.Equals(Path.GetPathRoot(full)?.TrimEnd('\\', '/'), full.TrimEnd('\\', '/'),
                StringComparison.OrdinalIgnoreCase))
        {
            return "Bitte nicht direkt in das Stammverzeichnis eines Laufwerks installieren, "
                + "sondern in einen Ordner darin (z. B. C:\\PraxisZeit).";
        }

        if (File.Exists(full))
        {
            return "Unter diesem Pfad liegt eine Datei. Bitte einen Ordner wählen.";
        }

        if (Directory.Exists(full) && Directory.EnumerateFileSystemEntries(full).Any())
        {
            return "Dieser Ordner existiert bereits und ist nicht leer. Aus Sicherheitsgründen "
                + "installiert PraxisZeit nur in einen neuen oder leeren Ordner – Dateien, die "
                + "vorher jemand dort abgelegt hat, würden sonst mit Systemrechten ausgeführt. "
                + "Bitte einen anderen Ordner wählen oder den Ordner zuerst löschen.";
        }

        return null;
    }

    /// <summary>
    /// icacls-Aufrufe fuer den (leeren) Installationsordner, in dieser
    /// Reihenfolge: Eigentuemer, Grants, Entfernungen, zuletzt
    /// <c>/inheritance:r</c>. Gleiche Rechte wie <c>praxiszeit-server.py</c>
    /// (<c>_build_install_acl_plan</c>, Wurzel); SIDs statt Namen.
    /// </summary>
    public static IReadOnlyList<string[]> RootHardeningCommands(string installDir) =>
    [
        ["icacls", installDir, "/setowner", SidAdministrators],
        ["icacls", installDir, "/grant:r", $"{SidSystem}:(OI)(CI)F"],
        ["icacls", installDir, "/grant:r", $"{SidAdministrators}:(OI)(CI)F"],
        ["icacls", installDir, "/grant:r", $"{SidUsers}:(OI)(CI)RX"],
        ["icacls", installDir, "/grant:r", $"{SidNetworkService}:(OI)(CI)RX"],
        ["icacls", installDir, "/remove:g", SidAuthenticatedUsers],
        ["icacls", installDir, "/remove:g", SidEveryone],
        ["icacls", installDir, "/inheritance:r"],
    ];

    /// <summary>
    /// True fuer die Aufrufe, deren Scheitern die Installation abbricht
    /// (Eigentuemer, Grants, Vererbung); ein nicht vorhandener Eintrag beim
    /// Entfernen ist kein Fehler.
    /// </summary>
    public static bool IsMandatory(string[] command) => !command.Contains("/remove:g");
}
