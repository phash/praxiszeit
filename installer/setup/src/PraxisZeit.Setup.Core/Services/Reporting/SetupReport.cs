using System.Globalization;
using System.Text;

namespace PraxisZeit.Setup.Core.Services.Reporting;

/// <summary>Eingaben für die Meldung eines fehlgeschlagenen Setup-Laufs (#557).</summary>
public sealed record SetupReportInput(
    string AppVersion,
    string Os,
    string InstallMode,
    string Headline,
    string Summary,
    IReadOnlyList<string> LogLines,
    DateTime UtcNow,
    string InstallId);

/// <summary>
/// Meldung (mrd-report-1) eines fehlgeschlagenen Setup-/Update-Laufs. Vorschau =
/// Gesendetes: <see cref="Title"/> und <see cref="Description"/> stehen genau so in
/// <see cref="Fields"/>. Enthält nie den Meldeschlüssel (den fügt
/// <see cref="ReportSender"/> erst beim Senden hinzu).
/// </summary>
public sealed record SetupReport(string Title, string Description, IReadOnlyDictionary<string, string> Fields)
{
    public const int TitleMax = 200;
    public const int DescriptionMax = 20000;
    public const int MaxLogLines = 200;
    public const string Target = "Ziel: POST https://report.mr-development.de/v1/reports (mrd-report-1)";
    private const string Intro = "Der Setup-Assistent meldet einen fehlgeschlagenen Lauf.";
    private const int OsMax = 32;

    public static SetupReport Build(SetupReportInput input)
    {
        var lines = input.LogLines.Count > MaxLogLines
            ? input.LogLines.Skip(input.LogLines.Count - MaxLogLines).ToList()
            : input.LogLines.ToList();

        // Einmal über die fertig zusammengesetzte Beschreibung bereinigen (nie
        // Teil für Teil); zu lang -> älteste Zeilen (ein Viertel, mind. eine) weg.
        var description = ReportSanitizer.SanitizePraxisZeit(Compose(input, lines));
        while (description.Length > DescriptionMax && lines.Count > 0)
        {
            lines.RemoveRange(0, Math.Max(1, lines.Count / 4));
            description = ReportSanitizer.SanitizePraxisZeit(Compose(input, lines));
        }
        if (description.Length > DescriptionMax)
        {
            description = description[..DescriptionMax];
        }

        var title = ReportSanitizer.SanitizePraxisZeit($"Setup fehlgeschlagen: {input.InstallMode} {input.AppVersion}".Trim());
        if (title.Length > TitleMax)
        {
            title = ReportSanitizer.SanitizePraxisZeit(title[..(TitleMax - 1)] + "…");
            title = title.Length > TitleMax ? title[..TitleMax] : title;
        }

        var os = ReportSanitizer.SanitizePraxisZeit(input.Os.Trim());
        var fields = new Dictionary<string, string>
        {
            ["protocol"] = "mrd-report-1",
            ["product"] = "praxiszeit",
            ["component"] = "setup",
            ["kind"] = "crash",
            ["severity"] = "high",
            ["install_id"] = input.InstallId,
            ["title"] = title,
            ["description"] = description,
            ["app_version"] = ReportSanitizer.SanitizePraxisZeit(input.AppVersion.Trim()),
            ["os"] = os.Length > OsMax ? os[..OsMax] : os,
        };
        return new SetupReport(title, description, fields);
    }

    private static string Compose(SetupReportInput input, IReadOnlyList<string> lines)
    {
        var parts = new List<string>
        {
            Intro,
            "",
            "---- Kontext (automatisch) ----",
            $"Produkt: PraxisZeit {input.AppVersion} (stable)",
            $"System: {input.Os}, Installationsart: native",
            $"Zeit: {Utc(input.UtcNow).ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture)}",
            $"Fehler: {input.Headline} – {input.Summary}",
            $"Protokoll (bereinigt, letzte {lines.Count} Zeilen):",
        };
        parts.AddRange(lines);
        return string.Join("\n", parts);
    }

    private static DateTime Utc(DateTime t) => t.Kind switch
    {
        DateTimeKind.Utc => t,
        DateTimeKind.Local => t.ToUniversalTime(),
        _ => DateTime.SpecifyKind(t, DateTimeKind.Utc),
    };

    /// <summary>Vorschlag für „Als Datei speichern“ (lokale Zeit).</summary>
    public static string FileName(DateTime localNow) =>
        $"praxiszeit-setup-meldung-{localNow.ToString("yyyyMMdd-HHmm", CultureInfo.InvariantCulture)}.txt";

    /// <summary>
    /// Text der gespeicherten Datei, gleiches Layout wie im Browser
    /// (<c>frontend/src/utils/reportFile.ts</c>): Kopf, Felder ohne title/description/
    /// credential sortiert, Titel, Beschreibung.
    /// </summary>
    public string ToFileText(DateTime? utcNow = null)
    {
        var now = Utc(utcNow ?? DateTime.UtcNow);
        var sb = new List<string>
        {
            "PraxisZeit – Problemmeldung (nicht gesendet)",
            $"Erstellt: {now.ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", CultureInfo.InvariantCulture)}",
            Target,
        };
        foreach (var key in Fields.Keys
                     .Where(k => k is not ("title" or "description")
                                 && !k.Contains("credential", StringComparison.OrdinalIgnoreCase))
                     .OrderBy(k => k, StringComparer.Ordinal))
        {
            sb.Add($"{key}: {Fields[key]}");
        }
        sb.Add("");
        sb.Add($"Titel: {Title}");
        sb.Add("");
        sb.Add(Description);
        return string.Join("\n", sb);
    }

    /// <summary>
    /// Vorschau im Setup-Fenster: Titel, Beschreibung und alle gesendeten Felder;
    /// der Meldeschlüssel nur als Platzhalter, nie im Klartext.
    /// </summary>
    public string ToPreviewText(bool withKey)
    {
        var sb = new StringBuilder();
        sb.Append("Titel: ").Append(Title).Append('\n').Append('\n');
        sb.Append(Description).Append('\n').Append('\n');
        sb.Append("Gesendete Felder:").Append('\n');
        foreach (var key in Fields.Keys
                     .Where(k => k is not ("title" or "description"))
                     .OrderBy(k => k, StringComparer.Ordinal))
        {
            sb.Append(key).Append(": ").Append(Fields[key]).Append('\n');
        }
        if (withKey)
        {
            sb.Append("credential: mrk_praxiszeit_… (nicht angezeigt)").Append('\n');
        }
        return sb.ToString().TrimEnd('\n');
    }
}
