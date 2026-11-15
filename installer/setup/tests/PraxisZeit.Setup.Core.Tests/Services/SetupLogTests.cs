using FluentAssertions;
using PraxisZeit.Setup.Core.Services;

namespace PraxisZeit.Setup.Core.Tests.Services;

public class SetupLogTests : IDisposable
{
    private readonly string _dir = Path.Combine(Path.GetTempPath(), $"pz-setuplog-{Guid.NewGuid():N}");

    public void Dispose()
    {
        if (Directory.Exists(_dir)) Directory.Delete(_dir, recursive: true);
        GC.SuppressFinalize(this);
    }

    private sealed class Collect : IProgress<RunnerEvent>
    {
        public List<RunnerEvent> Events { get; } = [];
        public void Report(RunnerEvent value) => Events.Add(value);
    }

    [Fact]
    public void Writes_every_event_to_logs_folder_and_forwards_it()
    {
        var inner = new Collect();
        var log = new SetupLog(inner, _dir, new DateTime(2026, 11, 15, 13, 22, 0));

        log.Report(new RunnerLogEvent("FEHLER: robocopy exit=8"));
        log.Report(new RunnerStepEvent("pip", RunnerStepStatus.Fail));
        log.Report(new RunnerDoneEvent(false));

        inner.Events.Should().HaveCount(3);
        log.FilePath.Should().Be(Path.Combine(_dir, "logs", "setup-20261115-132200.log"));
        var text = File.ReadAllText(log.FilePath!);
        text.Should().Contain("FEHLER: robocopy exit=8");
        text.Should().Contain("pip");
        text.Should().Contain("Fail");
        text.Should().Contain("fehlgeschlagen");
    }

    [Fact]
    public void Unwritable_target_never_breaks_the_setup()
    {
        var inner = new Collect();
        // Ein Datei-Pfad als "Ordner" laesst sich nicht anlegen.
        var blocker = Path.Combine(Path.GetTempPath(), $"pz-blocker-{Guid.NewGuid():N}");
        File.WriteAllText(blocker, "");
        try
        {
            var log = new SetupLog(inner, blocker, DateTime.Now);
            log.Report(new RunnerLogEvent("weiter"));
            inner.Events.Should().ContainSingle();
        }
        finally
        {
            File.Delete(blocker);
        }
    }
}
