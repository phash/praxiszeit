import React from 'react';

interface State {
  hasError: boolean;
}

export default class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  State
> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-gray-100">
          <div className="bg-white rounded-xl shadow-lg p-8 max-w-md w-full text-center">
            <h1 className="text-xl font-bold text-gray-800 mb-2">
              Etwas ist schiefgelaufen
            </h1>
            <p className="text-gray-500 mb-6">
              Ein unerwarteter Fehler ist aufgetreten.
            </p>
            <button
              onClick={() => window.location.reload()}
              className="px-5 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark transition"
            >
              Seite neu laden
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
