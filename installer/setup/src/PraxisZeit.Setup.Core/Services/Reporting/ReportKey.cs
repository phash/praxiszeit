using System.Reflection;

namespace PraxisZeit.Setup.Core.Services.Reporting;

/// <summary>
/// Meldeschlüssel (mrd-report-1, #557) aus der Build-Konstante <c>MrdReportKey</c>
/// (<c>dotnet publish -p:MrdReportKey=…</c> → <see cref="AssemblyMetadataAttribute"/>
/// der Setup-EXE). Ohne Schlüssel bietet das Setup nur „Als Datei speichern“.
/// Der Wert wird nie protokolliert oder angezeigt.
/// </summary>
public static class ReportKey
{
    public const string MetadataName = "MrdReportKey";

    private static readonly Lazy<string?> Cached = new(() => FromAssembly(Assembly.GetEntryAssembly()));

    public static string? Value => Cached.Value;

    public static string? FromAssembly(Assembly? assembly)
    {
        if (assembly is null)
        {
            return null;
        }
        try
        {
            var raw = assembly.GetCustomAttributes<AssemblyMetadataAttribute>()
                .FirstOrDefault(a => a.Key == MetadataName)?.Value;
            return Normalize(raw);
        }
        catch (Exception)
        {
            return null;
        }
    }

    public static string? Normalize(string? raw) =>
        string.IsNullOrWhiteSpace(raw) ? null : raw.Trim();
}
