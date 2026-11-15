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

    public string? FilePath { get; }

    public SetupLog(IProgress<RunnerEvent> inner, string installDir, DateTime startedAt)
    {
        _inner = inner;
        try
        {
            var logs = Path.Combine(installDir, "logs");
            Directory.CreateDirectory(logs);
            FilePath = Path.Combine(logs, $"setup-{startedAt:yyyyMMdd-HHmmss}.log");
        }
        catch (Exception)
        {
            _broken = true;
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
