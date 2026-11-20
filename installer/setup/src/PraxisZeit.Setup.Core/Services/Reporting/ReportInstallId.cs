namespace PraxisZeit.Setup.Core.Services.Reporting;

/// <summary>
/// Installations-ID (UUIDv4, klein) für Meldungen des Setup-Assistenten (#557).
/// Ablage <c>%LOCALAPPDATA%\PraxisZeit\report-install-id</c>, sonst eine frische ID nur
/// im Speicher. Ungültiger Inhalt wird ersetzt. Wirft nie.
/// </summary>
public static class ReportInstallId
{
    public const string FileName = "report-install-id";

    /// <param name="baseDir">Nur für Tests: ersetzt beide Standardorte.</param>
    public static string GetOrCreate(string? baseDir = null)
    {
        IEnumerable<string> bases = baseDir is not null ? [baseDir] : StorageBases();
        foreach (var b in bases.Where(b => !string.IsNullOrWhiteSpace(b)))
        {
            var id = TryAt(Path.Combine(b, "PraxisZeit", FileName));
            if (id is not null)
            {
                return id;
            }
        }
        return NewId();
    }

    /// <summary>
    /// Standardorte der ID-Datei. Bewusst NICHT <c>%ProgramData%</c>: dort legen
    /// normale Benutzer Ordner an, die ihnen gehören — der erhöhte Setup-Prozess
    /// ließe sich per Junction-Tausch (TOCTOU zwischen Prüfung und Schreiben) umlenken
    /// und die ID ließe sich vorbelegen. <c>%LOCALAPPDATA%</c> des ausführenden
    /// Kontos ist für andere Benutzer nicht beschreibbar (Review F23).
    /// </summary>
    public static IReadOnlyList<string> StorageBases() =>
        [Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData)];

    private static string? TryAt(string path)
    {
        var dir = Path.GetDirectoryName(path)!;
        string? temp = null;
        try
        {
            // Das Setup läuft erhöht. Eine vorab gelegte Verknüpfung (Junction/Symlink) als
            // Ordner oder Datei würde den Schreibzugriff umlenken -> Ort meiden.
            if (IsReparsePoint(dir) || IsReparsePoint(path))
            {
                return null;
            }
            if (File.Exists(path))
            {
                var existing = File.ReadAllText(path).Trim();
                if (IsValid(existing))
                {
                    return existing;
                }
            }
            Directory.CreateDirectory(dir);
            if (IsReparsePoint(dir))
            {
                return null;
            }
            var id = NewId();
            // Nie durch eine bestehende Datei schreiben (harter Link): neue
            // Datei anlegen (CreateNew folgt keiner vorhandenen Verknüpfung),
            // dann den Verzeichniseintrag ersetzen.
            temp = Path.Combine(dir, $".{FileName}-{Guid.NewGuid():N}.tmp");
            using (var fs = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                fs.Write(System.Text.Encoding.ASCII.GetBytes(id));
            }
            File.Move(temp, path, overwrite: true);
            temp = null;
            return id;
        }
        catch (Exception)
        {
            return null;
        }
        finally
        {
            if (temp is not null)
            {
                try { File.Delete(temp); } catch (Exception) { /* best effort */ }
            }
        }
    }

    private static bool IsReparsePoint(string path)
    {
        var info = new FileInfo(path);
        return info.Exists || Directory.Exists(path)
            ? info.Attributes.HasFlag(FileAttributes.ReparsePoint) || info.LinkTarget is not null
            : info.LinkTarget is not null; // Verknüpfung ins Leere
    }

    private static string NewId() => Guid.NewGuid().ToString("D");

    public static bool IsValid(string? value) =>
        value is { Length: 36 }
        && Guid.TryParseExact(value, "D", out _)
        && value == value.ToLowerInvariant()
        && value[14] == '4'
        && value[19] is '8' or '9' or 'a' or 'b';
}
