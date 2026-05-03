using System.Globalization;
using Avalonia.Data.Converters;
using Avalonia.Media;
using PraxisZeit.Setup.Core.Services;

namespace PraxisZeit.Setup.ViewModels;

/// <summary>
/// Konverter fuer die Step-Liste in der Progress-Page. Mappt
/// <see cref="RunnerStepStatus"/> auf Marker-Glyph (Pending/dot, Running/Spinner-Surrogat,
/// Ok/Haken, Warn/Ausrufezeichen, Fail/X), Hintergrund-Brush und Titel-
/// Vordergrund-Brush.
/// </summary>
public sealed class StepStatusToIconConverter : IValueConverter
{
    public object? Convert(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        value is RunnerStepStatus s ? IconFor(s) : "";

    public object? ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();

    private static string IconFor(RunnerStepStatus s) => s switch
    {
        RunnerStepStatus.Running => "...",
        RunnerStepStatus.Ok => "OK",
        RunnerStepStatus.Warn => "!",
        RunnerStepStatus.Fail => "X",
        _ => "",
    };
}

public sealed class StepStatusToBrushConverter : IValueConverter
{
    private static readonly IBrush Pending = new SolidColorBrush(Color.Parse("#C6CDD7"));
    private static readonly IBrush Running = new SolidColorBrush(Color.Parse("#0E5BA8"));
    private static readonly IBrush Ok = new SolidColorBrush(Color.Parse("#13B981"));
    private static readonly IBrush Warn = new SolidColorBrush(Color.Parse("#F59E0B"));
    private static readonly IBrush Fail = new SolidColorBrush(Color.Parse("#DC2626"));

    public object? Convert(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        value is RunnerStepStatus s ? BrushFor(s) : Pending;

    public object? ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();

    private static IBrush BrushFor(RunnerStepStatus s) => s switch
    {
        RunnerStepStatus.Running => Running,
        RunnerStepStatus.Ok => Ok,
        RunnerStepStatus.Warn => Warn,
        RunnerStepStatus.Fail => Fail,
        _ => Pending,
    };
}

public sealed class StepStatusToTitleBrushConverter : IValueConverter
{
    private static readonly IBrush Pending = new SolidColorBrush(Color.Parse("#8A95A4"));
    private static readonly IBrush Active = new SolidColorBrush(Color.Parse("#1A2332"));

    public object? Convert(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        value is RunnerStepStatus s ? (s == RunnerStepStatus.Pending ? Pending : Active) : Pending;

    public object? ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}

/// <summary>
/// Sammel-Helper fuer XAML-Bindings die einen statischen Konverter brauchen.
/// Avalonia kann keine generischen IValueConverter-Instanzen ueber XAML
/// referenzieren, deswegen die Singleton-Instances als
/// <c>{x:Static StepStatusConverters.NameOfConverter}</c>.
/// </summary>
public static class StepStatusConverters
{
    /// <summary>
    /// TwoWay-faehiger String-Equality-Konverter fuer RadioButtons:
    /// IsChecked = true wenn Bound-String == ConverterParameter, und
    /// gibt bei IsChecked->true den Parameter als String zurueck.
    /// </summary>
    public static readonly IValueConverter StringEqualityConverter = new StringEqualityConverterImpl();

    /// <summary>
    /// Mappt null/leer auf false, sonst auf true — fuer IsVisible-Bindings.
    /// </summary>
    public static readonly IValueConverter NotNullVisibilityConverter = new NotNullVisibilityConverterImpl();

    private sealed class StringEqualityConverterImpl : IValueConverter
    {
        public object? Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        {
            var s = value as string;
            var p = parameter as string;
            return string.Equals(s, p, StringComparison.Ordinal);
        }

        public object? ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
        {
            // RadioButton-Click: IsChecked wird true → wir muessen den
            // ConverterParameter als neuen String ans Source-ViewModel
            // zurueckgeben. Wenn IsChecked auf false geht (anderer Button
            // wird aktiv), ignorieren wir das — der andere Convert-Aufruf
            // setzt den korrekten Wert.
            if (value is true && parameter is string p)
            {
                return p;
            }
            return Avalonia.Data.BindingOperations.DoNothing;
        }
    }

    private sealed class NotNullVisibilityConverterImpl : IValueConverter
    {
        public object? Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        {
            return value switch
            {
                null => false,
                string s => !string.IsNullOrEmpty(s),
                _ => true,
            };
        }

        public object? ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
            throw new NotSupportedException();
    }
}
