using Avalonia;
using Avalonia.Controls;
using Avalonia.Markup.Xaml;
using Avalonia.Platform.Storage;
using PraxisZeit.Setup.ViewModels;

namespace PraxisZeit.Setup.Views;

public partial class InstallLocationPageView : UserControl
{
    public InstallLocationPageView()
    {
        InitializeComponent();
    }

    private void InitializeComponent()
    {
        AvaloniaXamlLoader.Load(this);
    }

    /// <summary>
    /// Avalonia-Folder-Picker. Storage-API gibt es ab Avalonia 11 — wir
    /// muessen das aktuelle TopLevel haben um den Picker auf dem richtigen
    /// Window zu rendern. Bei Erfolg ueberschreibt der Picker den
    /// InstallPath im ViewModel.
    /// </summary>
    private async void OnBrowseClicked(object? sender, Avalonia.Interactivity.RoutedEventArgs e)
    {
        if (DataContext is not InstallLocationPageViewModel vm) return;
        var top = TopLevel.GetTopLevel(this);
        if (top is null) return;

        var startFolder = !string.IsNullOrWhiteSpace(vm.InstallPath)
            ? await top.StorageProvider.TryGetFolderFromPathAsync(vm.InstallPath)
            : null;

        var folders = await top.StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions
        {
            Title = "Zielverzeichnis fuer PraxisZeit waehlen",
            AllowMultiple = false,
            SuggestedStartLocation = startFolder,
        });

        if (folders.Count > 0 && folders[0].TryGetLocalPath() is { } localPath)
        {
            vm.InstallPath = localPath;
        }
    }
}
