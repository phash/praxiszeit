using CommunityToolkit.Mvvm.ComponentModel;

namespace PraxisZeit.Setup.ViewModels;

public sealed partial class DonePageViewModel : WizardPageBase
{
    public override string Key => "done";
    public override string Title => "Fertig";
    public override bool CanGoBack => false;
    public override string NextButtonText => "Schliessen";

    [ObservableProperty]
    public partial bool Success { get; set; } = true;

    [ObservableProperty]
    public partial string Summary { get; set; } = "PraxisZeit wurde erfolgreich eingerichtet.";

    [ObservableProperty]
    public partial string BrowserUrl { get; set; } = "https://localhost/";
}
