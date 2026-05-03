using Avalonia.Controls;
using Avalonia.Markup.Xaml;

namespace PraxisZeit.Setup.Views;

public partial class PortsPageView : UserControl
{
    public PortsPageView()
    {
        InitializeComponent();
    }

    private void InitializeComponent()
    {
        AvaloniaXamlLoader.Load(this);
    }
}
