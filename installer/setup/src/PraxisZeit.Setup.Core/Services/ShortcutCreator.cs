namespace PraxisZeit.Setup.Core.Services;

/// <summary>
/// Erstellt Windows-Internet-Verknüpfungen (<c>.url</c>) auf den öffentlichen
/// Desktop und/oder ins Startmenü (All Users), die den Browser auf die lokale
/// PraxisZeit-Instanz öffnen.
///
/// <para>
/// Bewusst <c>.url</c> statt <c>.lnk</c>: eine Internet-Verknüpfung ist eine
/// reine INI-artige Textdatei und kommt ohne COM-Interop (IWshShell) aus —
/// 100 % deterministisch und test­bar. Das Ziel ist eine URL, kein Programm,
/// also ist <c>.url</c> ohnehin das passende Format.
/// </para>
/// </summary>
public static class ShortcutCreator
{
    /// <summary>Dateiname der Verknüpfung (Anzeigename ohne Endung: "PraxisZeit").</summary>
    public const string LinkFileName = "PraxisZeit.url";

    /// <summary>Serialisiert eine .url-Internet-Verknüpfung auf die angegebene URL.</summary>
    public static string Serialize(string url)
    {
        if (string.IsNullOrWhiteSpace(url))
        {
            throw new ArgumentException("URL darf nicht leer sein.", nameof(url));
        }
        // CRLF + abschließende Leerzeile — wie von Windows erzeugt.
        return $"[InternetShortcut]\r\nURL={url}\r\n";
    }

    /// <summary>Schreibt die Verknüpfung in <paramref name="directory"/>. Gibt den
    /// Pfad zurück oder null, wenn das Verzeichnis nicht ermittelbar war.</summary>
    public static string? WriteTo(string? directory, string url)
    {
        if (string.IsNullOrEmpty(directory))
        {
            return null;
        }
        Directory.CreateDirectory(directory);
        var path = Path.Combine(directory, LinkFileName);
        File.WriteAllText(path, Serialize(url));
        return path;
    }

    /// <summary>Verknüpfung auf den öffentlichen Desktop (All Users).</summary>
    public static string? CreateDesktopShortcut(string url)
        => WriteTo(Environment.GetFolderPath(Environment.SpecialFolder.CommonDesktopDirectory), url);

    /// <summary>Verknüpfung ins Startmenü (All Users → Programme).</summary>
    public static string? CreateStartMenuShortcut(string url)
        => WriteTo(Environment.GetFolderPath(Environment.SpecialFolder.CommonPrograms), url);
}
