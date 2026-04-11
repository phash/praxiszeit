using System.IO.Compression;

namespace PraxisZeit.Setup.Core.Services;

/// <summary>
/// Entpackt das Payload-ZIP (<c>praxiszeit-&lt;version&gt;-&lt;rid&gt;.zip</c>)
/// ins Zielverzeichnis. Im Update-Modus werden User-Daten und Secrets
/// ausgeschlossen — analog zu dem robocopy-Excludes im alten
/// update-wizard.ps1.
/// </summary>
public sealed class PayloadExtractor
{
    /// <summary>
    /// Paths (relativ zum Ziel-Install-Root), die im Update-Modus nie
    /// ueberschrieben werden, weil sie User-Daten oder Secrets enthalten.
    /// </summary>
    public static readonly IReadOnlySet<string> UpdateSkipPaths = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
    {
        "data",
        "logs",
        Path.Combine("config", "ssl"),
        Path.Combine("config", "praxiszeit.conf"),
        Path.Combine("config", ".db-credentials"),
        Path.Combine("config", ".secret-key"),
        Path.Combine("config", "license.key"),
    };

    public async Task ExtractAsync(
        string zipPath,
        string targetDirectory,
        bool isUpdate,
        IProgress<double>? progress = null,
        CancellationToken ct = default)
    {
        if (!File.Exists(zipPath))
        {
            throw new FileNotFoundException($"Payload not found: {zipPath}", zipPath);
        }

        Directory.CreateDirectory(targetDirectory);

        using var archive = ZipFile.OpenRead(zipPath);
        var totalEntries = archive.Entries.Count;
        var processed = 0;

        foreach (var entry in archive.Entries)
        {
            ct.ThrowIfCancellationRequested();

            // Directories werden durch File.WriteAllBytes / Create implizit erstellt
            if (string.IsNullOrEmpty(entry.Name))
            {
                processed++;
                continue;
            }

            var relativePath = entry.FullName.Replace('/', Path.DirectorySeparatorChar);
            var destPath = Path.Combine(targetDirectory, relativePath);

            if (isUpdate && ShouldSkipOnUpdate(relativePath))
            {
                processed++;
                continue;
            }

            var destDir = Path.GetDirectoryName(destPath);
            if (!string.IsNullOrEmpty(destDir))
            {
                Directory.CreateDirectory(destDir);
            }

            using (var source = entry.Open())
            await using (var target = File.Create(destPath))
            {
                await source.CopyToAsync(target, ct).ConfigureAwait(false);
            }

            processed++;
            progress?.Report((double)processed / totalEntries);
        }
    }

    private static bool ShouldSkipOnUpdate(string relativePath)
    {
        foreach (var skip in UpdateSkipPaths)
        {
            if (relativePath.StartsWith(skip, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }
        return false;
    }
}
