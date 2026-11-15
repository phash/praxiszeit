using System.Text;

namespace PraxisZeit.Setup.Core.Services;

/// <summary>
/// Leitet jedes Runner-Ereignis an die Progress-Page weiter und schreibt es
/// zusaetzlich nach <c>&lt;Installationsordner&gt;\logs\setup-JJJJMMTT-hhmmss.log</c>.
/// Kundenfall 2026-11-15: Das Protokoll stand nur im Setup-Fenster; nach dem
/// Schliessen war die entscheidende FEHLER-Zeile weg, in <c>logs\</c> fehlte sie.
/// Schreibfehler werden geschluckt: Das Protokoll darf das Setup nie abbrechen.
/// </summary>
public sealed class SetupLog : IProgress<RunnerEvent>
{
    private readonly IProgress<RunnerEvent> _inner;
    private readonly object _lock = new();
    private bool _broken;

    public string? FilePath { get; private set; }

    private readonly string _fileName;

    /// <summary>Protokoll direkt unter <c>&lt;installDir&gt;\logs</c> (Update/Reparatur).</summary>
    public SetupLog(IProgress<RunnerEvent> inner, string installDir, DateTime startedAt)
        : this(inner, Path.Combine(installDir, "logs"), startedAt, isDirectory: true)
    {
    }

    private SetupLog(IProgress<RunnerEvent> inner, string logDir, DateTime startedAt, bool isDirectory)
    {
        _inner = inner;
        _fileName = $"setup-{startedAt:yyyyMMdd-HHmmss}.log";
        try
        {
            Directory.CreateDirectory(logDir);
            FilePath = Path.Combine(logDir, _fileName);
        }
        catch (Exception)
        {
            _broken = true;
        }
    }

    /// <summary>
    /// Erstinstallation: zuerst in <paramref name="tempDir"/> schreiben. Der
    /// Installationsordner muss bis zur Leerordner-Pruefung unberuehrt bleiben
    /// (Review 2026-11-15: ein vorab angelegtes logs\ blockierte jede
    /// Neuinstallation). Nach dem Lauf <see cref="RelocateTo"/> aufrufen.
    /// </summary>
    public static SetupLog Deferred(IProgress<RunnerEvent> inner, string tempDir, DateTime startedAt) =>
        new(inner, tempDir, startedAt, isDirectory: true);

    /// <summary>
    /// Verschiebt das Protokoll nach <c>&lt;installDir&gt;\logs</c>, sofern der
    /// Ordner existiert. Fehler werden geschluckt; das Protokoll bleibt dann
    /// unter dem bisherigen Pfad.
    /// </summary>
    public void RelocateTo(string installDir)
    {
        lock (_lock)
        {
            if (FilePath is null || !Directory.Exists(installDir))
            {
                return;
            }
            try
            {
                var logs = Path.Combine(installDir, "logs");
                var target = Path.Combine(logs, _fileName);
                if (string.Equals(Path.GetFullPath(target), Path.GetFullPath(FilePath), StringComparison.OrdinalIgnoreCase))
                {
                    return;
                }
                Directory.CreateDirectory(logs);
                if (File.Exists(FilePath))
                {
                    File.Move(FilePath, target, overwrite: true);
                }
                FilePath = target;
                _broken = false;
            }
            catch (Exception)
            {
                // Protokoll bleibt am alten Ort.
            }
        }
    }

    public void Report(RunnerEvent value)
    {
        Write(value);
        _inner.Report(value);
    }

    private void Write(RunnerEvent value)
    {
        if (_broken || FilePath is null)
        {
            return;
        }
        var text = value switch
        {
            RunnerLogEvent l => l.Message,
            RunnerStepEvent s => $"[Schritt {s.Id}: {s.Status}]",
            RunnerDoneEvent d => d.Success ? "[Ergebnis: erfolgreich]" : "[Ergebnis: fehlgeschlagen]",
            _ => null,
        };
        if (text is null)
        {
            return;
        }
        lock (_lock)
        {
            try
            {
                File.AppendAllText(FilePath, $"{DateTime.Now:HH:mm:ss} {text}{Environment.NewLine}", Encoding.UTF8);
            }
            catch (Exception)
            {
                _broken = true;
            }
        }
    }
}
