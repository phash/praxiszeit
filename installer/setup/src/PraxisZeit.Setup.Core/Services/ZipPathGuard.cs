namespace PraxisZeit.Setup.Core.Services;

/// <summary>
/// Schutz gegen "Zip Slip" (Audit 2026-11-07 S3-16): ein ZIP-Eintrag wie
/// <c>..\..\Windows\System32\x.dll</c> oder ein absoluter Pfad darf nie
/// ausserhalb des Zielverzeichnisses landen. Heute ist das Payload in die
/// signierte setup.exe eingebettet; die Pruefung greift, sobald ein externes
/// ZIP geladen wird (<see cref="PayloadExtractor"/> mit <c>zipPath</c>).
/// </summary>
public static class ZipPathGuard
{
    /// <summary>
    /// Liefert den vollen Zielpfad fuer <paramref name="entryFullName"/>
    /// unterhalb von <paramref name="targetDirectory"/>; wirft
    /// <see cref="InvalidDataException"/>, wenn der Eintrag hinausfuehrt.
    /// </summary>
    public static string ResolveEntryPath(string targetDirectory, string entryFullName)
    {
        var root = Path.GetFullPath(targetDirectory);
        var rootWithSep = root.EndsWith(Path.DirectorySeparatorChar)
            ? root
            : root + Path.DirectorySeparatorChar;
        // ZIP nutzt '/', Windows-Werkzeuge schreiben manchmal '\' - beides als
        // Trenner behandeln, damit "..\" auch unter Linux (Tests) erkannt wird.
        var relative = entryFullName.Replace('\\', '/').Replace('/', Path.DirectorySeparatorChar);
        if (Path.IsPathRooted(relative) || relative.Contains(':'))
        {
            throw new InvalidDataException($"ZIP-Eintrag mit absolutem Pfad abgelehnt: {entryFullName}");
        }
        var full = Path.GetFullPath(Path.Combine(root, relative));
        var comparison = OperatingSystem.IsWindows()
            ? StringComparison.OrdinalIgnoreCase
            : StringComparison.Ordinal;
        if (!full.StartsWith(rootWithSep, comparison))
        {
            throw new InvalidDataException($"ZIP-Eintrag ausserhalb des Zielverzeichnisses abgelehnt: {entryFullName}");
        }
        return full;
    }
}
