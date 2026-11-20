namespace PraxisZeit.Setup.Core.Services.Reporting;

/// <summary>
/// Installations-ID (UUIDv4, klein) für Meldungen des Setup-Assistenten (#557).
/// Ablage <c>%ProgramData%\PraxisZeit\report-install-id</c>, sonst
/// <c>%LOCALAPPDATA%\PraxisZeit\report-install-id</c>, sonst eine frische ID nur
/// im Speicher. Ungültiger Inhalt wird ersetzt. Wirft nie.
/// </summary>
public static class ReportInstallId
{
    public const string FileName = "report-install-id";

    /// <param name="baseDir">Nur für Tests: ersetzt beide Standardorte.</param>
    public static string GetOrCreate(string? baseDir = null)
    {
        IEnumerable<string> bases = baseDir is not null
            ? [baseDir]
            : [
                Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            ];
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

    private static string? TryAt(string path)
    {
        try
        {
            if (File.Exists(path))
            {
                var existing = File.ReadAllText(path).Trim();
                if (IsValid(existing))
                {
                    return existing;
                }
            }
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            var id = NewId();
            File.WriteAllText(path, id);
            return id;
        }
        catch (Exception)
        {
            return null;
        }
    }

    private static string NewId() => Guid.NewGuid().ToString("D");

    public static bool IsValid(string? value) =>
        value is { Length: 36 }
        && Guid.TryParseExact(value, "D", out _)
        && value == value.ToLowerInvariant()
        && value[14] == '4'
        && value[19] is '8' or '9' or 'a' or 'b';
}
