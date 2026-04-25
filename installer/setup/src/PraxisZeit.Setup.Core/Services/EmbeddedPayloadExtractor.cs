using System.IO.Compression;
using System.Reflection;

namespace PraxisZeit.Setup.Core.Services;

/// <summary>
/// Extrahiert das eingebettete Windows-Payload-ZIP (Python, PostgreSQL-Installer,
/// Backend, Frontend, .bat/.ps1-Scripts, nssm) aus dem Setup-Assembly nach einem
/// frischen Temp-Verzeichnis. Wird vom Avalonia-Wizard beim ersten Wechsel auf
/// die Progress-Page aufgerufen, BEVOR ScriptRunner setup.bat oder
/// update-wizard.ps1 startet.
///
/// <para>
/// Das ZIP wird als <see cref="EmbeddedResource"/> mit
/// <c>LogicalName="praxiszeit_payload.zip"</c> in <c>PraxisZeit.Setup.csproj</c>
/// eingebunden — nur wenn die MSBuild-Property <c>PayloadZipPath</c> gesetzt
/// ist (Build-Pipeline) und auf eine existierende Datei zeigt. Dev-Builds ohne
/// das Property haben kein eingebettetes Payload; <see cref="HasEmbeddedPayload"/>
/// gibt dann <c>false</c> zurueck.
/// </para>
/// </summary>
public sealed class EmbeddedPayloadExtractor
{
    public const string PayloadResourceName = "praxiszeit_payload.zip";

    private readonly Assembly _assembly;

    public EmbeddedPayloadExtractor()
        : this(Assembly.GetEntryAssembly() ?? Assembly.GetExecutingAssembly())
    {
    }

    public EmbeddedPayloadExtractor(Assembly assembly)
    {
        _assembly = assembly;
    }

    /// <summary>
    /// True falls ein Payload-ZIP in das Assembly eingebettet wurde
    /// (Production-Build via build-release.sh). Dev-Builds geben false.
    /// </summary>
    public bool HasEmbeddedPayload =>
        _assembly.GetManifestResourceNames()
            .Any(n => n.Equals(PayloadResourceName, StringComparison.OrdinalIgnoreCase));

    /// <summary>
    /// Liefert die ungefaehre Groesse des eingebetteten Payloads in Bytes
    /// (fuer Free-Space-Checks vor dem Extract).
    /// </summary>
    public long GetEmbeddedPayloadSize()
    {
        using var stream = _assembly.GetManifestResourceStream(PayloadResourceName);
        return stream?.Length ?? 0L;
    }

    /// <summary>
    /// Extrahiert das eingebettete ZIP nach einem frisch erzeugten Temp-Ordner
    /// (<c>%TEMP%\praxiszeit-setup-&lt;guid&gt;</c>) und gibt den Pfad zurueck.
    /// Der Aufrufer ist verantwortlich, den Ordner nach Abschluss zu loeschen
    /// (siehe <see cref="DeleteExtractedPayload"/>).
    /// </summary>
    public async Task<string> ExtractAsync(
        IProgress<double>? progress = null,
        CancellationToken ct = default)
    {
        if (!HasEmbeddedPayload)
        {
            throw new InvalidOperationException(
                $"No embedded payload resource '{PayloadResourceName}' in assembly. " +
                "Was the installer built without -p:PayloadZipPath? Dev builds need an external ZIP.");
        }

        var tempRoot = Path.Combine(
            Path.GetTempPath(),
            $"praxiszeit-setup-{Guid.NewGuid():N}");
        Directory.CreateDirectory(tempRoot);

        await using var resourceStream = _assembly.GetManifestResourceStream(PayloadResourceName)
            ?? throw new InvalidOperationException($"Resource stream null for '{PayloadResourceName}'");

        using var archive = new ZipArchive(resourceStream, ZipArchiveMode.Read, leaveOpen: false);
        var totalEntries = archive.Entries.Count;
        var processed = 0;

        foreach (var entry in archive.Entries)
        {
            ct.ThrowIfCancellationRequested();

            if (string.IsNullOrEmpty(entry.Name))
            {
                processed++;
                continue;
            }

            var relativePath = entry.FullName.Replace('/', Path.DirectorySeparatorChar);
            var destPath = Path.Combine(tempRoot, relativePath);

            var destDir = Path.GetDirectoryName(destPath);
            if (!string.IsNullOrEmpty(destDir))
            {
                Directory.CreateDirectory(destDir);
            }

            await using (var source = entry.Open())
            await using (var target = File.Create(destPath))
            {
                await source.CopyToAsync(target, ct).ConfigureAwait(false);
            }

            processed++;
            if (totalEntries > 0)
            {
                progress?.Report((double)processed / totalEntries);
            }
        }

        return tempRoot;
    }

    /// <summary>
    /// Loescht den vom <see cref="ExtractAsync"/> erzeugten Temp-Ordner
    /// idempotent. Schluckt Exceptions: wenn ein File noch von einem
    /// laufenden Subprocess gehalten wird, wird es beim naechsten
    /// Reboot via Windows-TempFolder-Cleanup entfernt.
    /// </summary>
    public static void DeleteExtractedPayload(string path)
    {
        if (string.IsNullOrEmpty(path) || !Directory.Exists(path))
        {
            return;
        }

        try
        {
            Directory.Delete(path, recursive: true);
        }
        catch
        {
            // best-effort: Temp-Ordner bleibt liegen, Windows raeumt auf
        }
    }
}
