using Avalonia.Controls;
using Avalonia.Markup.Xaml;
using Avalonia.Platform.Storage;
using PraxisZeit.Setup.ViewModels;

namespace PraxisZeit.Setup.Views;

public partial class LicensePageView : UserControl
{
    public LicensePageView()
    {
        InitializeComponent();
    }

    private void InitializeComponent()
    {
        AvaloniaXamlLoader.Load(this);
    }

    /// <summary>
    /// File-Picker fuer license.key (oder beliebige Text-Datei mit dem
    /// JWT). Liest den Inhalt direkt ein und schreibt ihn ins ViewModel —
    /// von dort triggert es die Live-Validierung.
    /// </summary>
    private async void OnLoadLicenseFileClicked(object? sender, Avalonia.Interactivity.RoutedEventArgs e)
    {
        if (DataContext is not LicensePageViewModel vm) return;
        var top = TopLevel.GetTopLevel(this);
        if (top is null) return;

        var files = await top.StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = "Lizenz-Datei wählen",
            AllowMultiple = false,
            FileTypeFilter =
            [
                new FilePickerFileType("Lizenz-Datei (*.key)") { Patterns = ["*.key"] },
                new FilePickerFileType("Alle Dateien")          { Patterns = ["*"] },
            ],
        });

        if (files.Count == 0) return;
        var file = files[0];
        try
        {
            await using var stream = await file.OpenReadAsync();
            using var reader = new StreamReader(stream);
            var text = await reader.ReadToEndAsync();
            vm.LoadFromFile(file.TryGetLocalPath() ?? file.Name, text);
        }
        catch (Exception ex)
        {
            vm.LicenseToken = string.Empty;
            vm.LoadedFromPath = $"FEHLER: {ex.Message}";
        }
    }
}
