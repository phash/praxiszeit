using System;
using System.IO;
using System.Threading.Tasks;
using Avalonia.Controls;
using Avalonia.Platform.Storage;
using PraxisZeit.Setup.ViewModels;

namespace PraxisZeit.Setup.Views;

public partial class DonePageView : UserControl
{
    public DonePageView()
    {
        InitializeComponent();
        DataContextChanged += (_, _) =>
        {
            if (DataContext is DonePageViewModel vm)
            {
                vm.SaveFileHandler = SaveTextAsync;
            }
        };
    }

    /// <summary>Dateidialog fuer "Als Datei speichern" (#557); true = geschrieben.</summary>
    private async Task<bool> SaveTextAsync(string suggestedName, string text)
    {
        var top = TopLevel.GetTopLevel(this);
        if (top is null)
        {
            return false;
        }
        var file = await top.StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions
        {
            Title = "Meldung speichern",
            SuggestedFileName = suggestedName,
            DefaultExtension = "txt",
            FileTypeChoices = new[] { new FilePickerFileType("Textdatei") { Patterns = new[] { "*.txt" } } },
        });
        if (file is null)
        {
            return false;
        }
        await using var stream = await file.OpenWriteAsync();
        stream.SetLength(0);
        await using var writer = new StreamWriter(stream, new System.Text.UTF8Encoding(false));
        await writer.WriteAsync(text);
        return true;
    }
}
