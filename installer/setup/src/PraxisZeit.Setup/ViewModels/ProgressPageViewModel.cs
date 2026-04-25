using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using PraxisZeit.Setup.Core.Services;

namespace PraxisZeit.Setup.ViewModels;

public sealed partial class StepItem : ObservableObject
{
    public required string Id { get; init; }
    public required string Title { get; init; }

    [ObservableProperty]
    public partial RunnerStepStatus Status { get; set; } = RunnerStepStatus.Pending;
}

public sealed partial class ProgressPageViewModel : WizardPageBase
{
    public override string Key => "progress";
    public override string Title => "Installation";
    public override bool CanGoBack => false;
    public override string NextButtonText => "Bitte warten...";

    public ObservableCollection<StepItem> Steps { get; } = [];

    [ObservableProperty]
    public partial string LogText { get; set; } = string.Empty;

    [ObservableProperty]
    public partial int Percent { get; set; }

    [ObservableProperty]
    public partial bool IsRunning { get; set; } = true;

    [ObservableProperty]
    public partial string Headline { get; set; } = "Installation laeuft";

    [ObservableProperty]
    public partial string SubHeadline { get; set; } = "Bitte warten Sie, bis alle Schritte abgeschlossen sind.";

    public ProgressPageViewModel()
    {
        // CanGoNext bleibt auf false, bis das Runner-DoneEvent eintrifft
        CanGoNext = false;
    }

    /// <summary>
    /// Befuellt die Step-Liste in Abhaengigkeit vom Modus. Update-Mode
    /// spiegelt die Reihenfolge in <c>update-wizard.ps1.Invoke-Update</c>
    /// (ACL → Backup → Stop → Copy → Pip → Start → Task), Fresh-Mode die
    /// Reihenfolge in <see cref="ScriptRunner.RunFreshInstallAsync"/>
    /// (Copy → Setup → Service → Start).
    /// </summary>
    public void InitializeSteps(Core.Models.InstallMode mode)
    {
        Steps.Clear();
        if (mode == Core.Models.InstallMode.FreshInstall || mode == Core.Models.InstallMode.Repair)
        {
            Steps.Add(new StepItem { Id = "copy",    Title = "1. Installationsdateien kopieren" });
            Steps.Add(new StepItem { Id = "setup",   Title = "2. PostgreSQL und Python einrichten" });
            Steps.Add(new StepItem { Id = "service", Title = "3. Service registrieren (Firewall, Backup-Task)" });
            Steps.Add(new StepItem { Id = "start",   Title = "4. Service starten" });
        }
        else // Update
        {
            Steps.Add(new StepItem { Id = "acl",    Title = "1. ACL-Fix fuer .db-credentials" });
            Steps.Add(new StepItem { Id = "backup", Title = "2. Datenbank-Backup erstellen" });
            Steps.Add(new StepItem { Id = "stop",   Title = "3. PraxisZeit-Service stoppen" });
            Steps.Add(new StepItem { Id = "copy",   Title = "4. Dateien aktualisieren" });
            Steps.Add(new StepItem { Id = "pip",    Title = "5. Python-Dependencies pruefen" });
            Steps.Add(new StepItem { Id = "start",  Title = "6. Service starten" });
            Steps.Add(new StepItem { Id = "task",   Title = "7. Backup-Task registrieren" });
        }
    }

    public void Apply(RunnerEvent e)
    {
        switch (e)
        {
            case RunnerStepEvent step:
                var item = Steps.FirstOrDefault(s => s.Id.Equals(step.Id, StringComparison.OrdinalIgnoreCase));
                if (item is not null)
                {
                    item.Status = step.Status;
                }
                break;
            case RunnerLogEvent log:
                AppendLog(log.Message);
                break;
            case RunnerProgressEvent prog:
                Percent = prog.Percent;
                break;
            case RunnerDoneEvent done:
                IsRunning = false;
                CanGoNext = true;
                Headline = done.Success ? "Installation abgeschlossen" : "Installation mit Fehlern beendet";
                SubHeadline = done.Success
                    ? "Alle Schritte erfolgreich. Klicken Sie auf 'Weiter' fuer den letzten Schritt."
                    : "Bitte pruefen Sie das Protokoll. Ein Backup der Datenbank liegt unter data\\backups.";
                OnPropertyChanged(nameof(NextButtonText));
                break;
        }
    }

    public override string ToString() => Headline;

    private const int MaxLogLines = 1000;

    private void AppendLog(string line)
    {
        var stamped = $"[{DateTime.Now:HH:mm:ss}] {line}";
        // Cheap line-cap: split + take last N. Bei sehr vielen Lines koennte
        // das teurer werden — wir setzen Maximal-Schwelle bewusst hoch (1000).
        if (string.IsNullOrEmpty(LogText))
        {
            LogText = stamped;
            return;
        }
        var combined = LogText + "\n" + stamped;
        var lines = combined.Split('\n');
        if (lines.Length > MaxLogLines)
        {
            combined = string.Join('\n', lines[^MaxLogLines..]);
        }
        LogText = combined;
    }
}
