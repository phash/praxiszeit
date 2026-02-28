import { useState, FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import { LogIn, FileText, Shield, Smartphone } from 'lucide-react';
import PasswordInput from '../components/PasswordInput';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [totpRequired, setTotpRequired] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const { login } = useAuthStore();
  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await login(username, password, totpRequired ? totpCode : undefined);
      navigate('/');
    } catch (err: any) {
      // F-019: backend signals "TOTP required" via X-Requires-TOTP header
      if (err.response?.headers?.['x-requires-totp'] === 'true') {
        setTotpRequired(true);
        // Don't show an error – just reveal the TOTP input field
      } else {
        setError(
          err.response?.data?.detail || 'Anmeldung fehlgeschlagen. Bitte versuchen Sie es erneut.'
        );
        if (totpRequired) setTotpCode(''); // Clear wrong TOTP code
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary to-primary-dark flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-8">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">PraxisZeit</h1>
          <p className="text-gray-600">Zeiterfassungssystem</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
              {error}
            </div>
          )}

          <div>
            <label htmlFor="username" className="block text-sm font-medium text-gray-700 mb-2">
              Benutzername
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent transition"
              placeholder="benutzername"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-2">
              Passwort
            </label>
            <PasswordInput
              id="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent transition"
              placeholder="••••••••"
            />
          </div>

          {/* F-019: TOTP field – revealed after first 401 with X-Requires-TOTP */}
          {totpRequired && (
            <div>
              <label htmlFor="totp-code" className="block text-sm font-medium text-gray-700 mb-2">
                <span className="flex items-center gap-1.5">
                  <Smartphone size={15} />
                  2FA-Code (Authenticator-App)
                </span>
              </label>
              <input
                id="totp-code"
                type="text"
                inputMode="numeric"
                pattern="\d{6}"
                maxLength={6}
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                required
                autoComplete="one-time-code"
                autoFocus
                className="w-full px-4 py-3 border border-blue-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent transition text-center text-xl tracking-widest font-mono"
                placeholder="000000"
              />
              <p className="mt-1 text-xs text-gray-500">
                Öffnen Sie Ihre Authenticator-App und geben Sie den 6-stelligen Code ein.
              </p>
            </div>
          )}

          <button
            type="submit"
            disabled={loading || (totpRequired && totpCode.length !== 6)}
            className="w-full bg-primary hover:bg-primary-dark text-white font-semibold py-3 px-4 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-2"
          >
            {loading ? (
              <span>Anmelden...</span>
            ) : (
              <>
                <LogIn size={20} />
                <span>Anmelden</span>
              </>
            )}
          </button>
        </form>

        <div className="mt-6 text-center text-sm text-gray-500">
          <p>Bei Problemen wenden Sie sich an Ihren Administrator</p>
        </div>

        <div className="mt-3 text-center">
          <Link
            to="/privacy"
            className="inline-flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 transition-colors"
          >
            <Shield size={12} />
            Datenschutzerklärung
          </Link>
        </div>

        <div className="mt-6 pt-5 border-t border-gray-100">
          <p className="text-xs text-gray-400 text-center mb-3">Dokumentation</p>
          <div className="flex justify-center gap-3 flex-wrap">
            <a
              href="/docs/Mitarbeiter-Handbuch.pdf"
              download
              className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-primary transition-colors"
            >
              <FileText size={13} />
              Mitarbeiter-Handbuch
            </a>
            <span className="text-gray-300">·</span>
            <a
              href="/docs/Cheat-Sheet.pdf"
              download
              className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-primary transition-colors"
            >
              <FileText size={13} />
              Cheat-Sheet
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
