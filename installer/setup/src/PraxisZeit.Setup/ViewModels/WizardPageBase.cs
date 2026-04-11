using CommunityToolkit.Mvvm.ComponentModel;

namespace PraxisZeit.Setup.ViewModels;

/// <summary>
/// Basis fuer alle Wizard-Seiten. Jede Page kennt ihren Titel (oben im
/// Step-Indicator angezeigt), ihren Key (fuer die Navigations-Logik)
/// und ob sie "weiter"- / "zurueck"-faehig ist (fuer Button-Enable-
/// State in der Shell).
/// </summary>
public abstract partial class WizardPageBase : ViewModelBase
{
    /// <summary>Key der Page — stable identifier fuer Navigation.</summary>
    public abstract string Key { get; }

    /// <summary>Menschenlesbarer Titel fuer den Step-Indicator.</summary>
    public abstract string Title { get; }

    /// <summary>
    /// Wird beim Betreten der Page gesetzt (MainWindowViewModel), damit
    /// die Page validierungs-lokal weiss ob "Weiter" jetzt aktiv sein darf.
    /// </summary>
    [ObservableProperty]
    public partial bool CanGoNext { get; set; } = true;

    /// <summary>Default: jede Page kann zurueck, ausser Welcome + Progress.</summary>
    public virtual bool CanGoBack => true;

    /// <summary>Text des "Weiter"-Buttons. Darf pro Page anders sein (z.B. "Installieren", "Schliessen").</summary>
    public virtual string NextButtonText => "Weiter";

    /// <summary>
    /// Hook der beim Verlassen der Page aufgerufen wird (fuer async
    /// Validation oder Persistieren von Werten). Default-Impl no-op.
    /// </summary>
    public virtual Task<bool> OnLeaveAsync(CancellationToken ct = default) => Task.FromResult(true);
}
