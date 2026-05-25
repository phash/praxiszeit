using System.Diagnostics;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace PraxisZeit.Setup.ViewModels;

public sealed partial class DonePageViewModel : WizardPageBase
{
    public override string Key => "done";
    public override string Title => "Fertig";
    public override bool CanGoBack => false;
    public override string NextButtonText => "Schließen";

    [ObservableProperty]
    public partial bool Success { get; set; } = true;

    [ObservableProperty]
    public partial string Headline { get; set; } = "Fertig!";

    [ObservableProperty]
    public partial string Summary { get; set; } = "PraxisZeit wurde erfolgreich eingerichtet.";

    [ObservableProperty]
    public partial string BrowserUrl { get; set; } = "https://localhost/";

    public bool ShowBrowserCard => Success;
    public bool ShowErrorCard => !Success;

    partial void OnSuccessChanged(bool value)
    {
        OnPropertyChanged(nameof(ShowBrowserCard));
        OnPropertyChanged(nameof(ShowErrorCard));
    }

    [RelayCommand]
    private void OpenBrowser()
    {
        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = BrowserUrl,
                UseShellExecute = true,
            });
        }
        catch
        {
            // best-effort: wenn der Default-Browser fehlt zeigen wir
            // weiterhin nur die URL — kein Crash.
        }
    }
}
