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

    [Fact]
    public void Deferred_log_leaves_install_dir_untouched_until_relocated()
    {
        // Review 2026-11-15: Bei der Erstinstallation legte das Protokoll
        // logs\ an, bevor InstallDirGuard den Zielordner pruefte - jede
        // Neuinstallation scheiterte an "Ordner ist nicht leer".
        var inner = new Collect();
        var temp = Path.Combine(_dir, "temp");
        var install = Path.Combine(_dir, "install");
        var log = SetupLog.Deferred(inner, temp, new DateTime(2026, 11, 15, 18, 0, 0));

        log.Report(new RunnerLogEvent("Entpacke Installationspaket..."));

        Directory.Exists(install).Should().BeFalse();
        InstallDirGuard.FreshTargetProblem(install).Should().BeNull();

        Directory.CreateDirectory(install);
        log.RelocateTo(install);
        log.Report(new RunnerLogEvent("danach"));

        log.FilePath.Should().Be(Path.Combine(install, "logs", "setup-20261115-180000.log"));
        var text = File.ReadAllText(log.FilePath!);
        text.Should().Contain("Entpacke Installationspaket...");
        text.Should().Contain("danach");
        Directory.GetFiles(temp).Should().BeEmpty();
    }

    [Fact]
    public void Relocate_without_install_dir_keeps_temp_file()
    {
        var inner = new Collect();
        var temp = Path.Combine(_dir, "temp");
        var log = SetupLog.Deferred(inner, temp, DateTime.Now);
        log.Report(new RunnerLogEvent("x"));
        var before = log.FilePath;

        log.RelocateTo(Path.Combine(_dir, "missing"));

        log.FilePath.Should().Be(before);
        File.Exists(before!).Should().BeTrue();
    }
}
