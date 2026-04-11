using Avalonia.Controls;
using PraxisZeit.Setup.ViewModels;

namespace PraxisZeit.Setup.Views;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        DataContextChanged += OnDataContextChanged;
    }

    private void OnDataContextChanged(object? sender, System.EventArgs e)
    {
        if (DataContext is MainWindowViewModel vm)
        {
            vm.CloseRequested += Close;
        }
    }
}
