import { useState, FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { UserPlus } from 'lucide-react';
import apiClient from '../api/client';
import { useSystemStore } from '../stores/systemStore';
import PasswordInput from '../components/PasswordInput';
import { getErrorMessage } from '../utils/errorMessage';

/**
 * /signup — Self-service practice registration. Shown only when
 * deployment_mode=saas; on-prem installs can't reach this route because
 * the backend returns 404 for /api/public/signup.
 */
export default function Signup() {
  const deploymentMode = useSystemStore((s) => s.info?.deployment_mode);

  const [practiceName, setPracticeName] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [country, setCountry] = useState('DE');
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [acceptPrivacy, setAcceptPrivacy] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  if (deploymentMode === 'onprem') {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-gray-50">
        <div className="max-w-md bg-white rounded-xl shadow-card p-8 text-center">
          <h1 className="text-xl font-semibold mb-2">Registrierung nicht verfügbar</h1>
          <p className="text-sm text-gray-600 mb-4">
            Diese Installation läuft im Lokalmodus. Eine Selbstregistrierung ist nur auf der SaaS-Plattform möglich.
          </p>
          <Link to="/login" className="text-primary hover:underline">Zum Login</Link>
        </div>
      </div>
    );
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await apiClient.post('/public/signup', {
        practice_name: practiceName,
        admin_email: email,
        admin_first_name: firstName,
        admin_last_name: lastName,
        admin_password: password,
        accept_terms: acceptTerms,
        accept_privacy: acceptPrivacy,
        country,
      });
      setSubmitted(true);
    } catch (err: any) {
      setError(getErrorMessage(err, 'Registrierung fehlgeschlagen. Bitte versuche es erneut.'));
    } finally {
      setLoading(false);
    }
  }

  if (submitted) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-gray-50">
        <div className="max-w-md bg-white rounded-xl shadow-card p-8 text-center">
          <h1 className="text-xl font-semibold mb-2">Fast geschafft!</h1>
          <p className="text-sm text-gray-600 mb-4">
            Wir haben dir eine E-Mail mit einem Bestätigungslink gesendet.
            Der Link ist 24 Stunden gültig.
          </p>
          <Link to="/login" className="text-primary hover:underline">Zum Login</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-gray-50">
      <form onSubmit={handleSubmit} className="w-full max-w-md bg-white rounded-xl shadow-card p-8 space-y-4">
        <div className="flex items-center gap-2 mb-4">
          <UserPlus className="text-primary" />
          <h1 className="text-xl font-semibold">Praxis registrieren</h1>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Praxisname</label>
          <input
            type="text" required value={practiceName}
            onChange={(e) => setPracticeName(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-hidden focus:ring-2 focus:ring-primary"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Vorname</label>
            <input
              type="text" required value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-hidden focus:ring-2 focus:ring-primary"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Nachname</label>
            <input
              type="text" required value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-hidden focus:ring-2 focus:ring-primary"
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">E-Mail-Adresse (Admin)</label>
          <input
            type="email" required value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-hidden focus:ring-2 focus:ring-primary"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Passwort</label>
          <PasswordInput
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-hidden focus:ring-2 focus:ring-primary"
          />
          <p className="text-xs text-gray-500 mt-1">Mindestens 8 Zeichen.</p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Land</label>
          <select
            value={country}
            onChange={(e) => setCountry(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-hidden focus:ring-2 focus:ring-primary"
          >
            <option value="DE">Deutschland</option>
            <option value="AT">Österreich</option>
            <option value="CH">Schweiz</option>
          </select>
        </div>

        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox" required checked={acceptTerms}
            onChange={(e) => setAcceptTerms(e.target.checked)}
            className="mt-1"
          />
          <span>Ich akzeptiere die <Link to="/privacy" className="text-primary hover:underline">AGB</Link>.</span>
        </label>

        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox" required checked={acceptPrivacy}
            onChange={(e) => setAcceptPrivacy(e.target.checked)}
            className="mt-1"
          />
          <span>Ich akzeptiere die <Link to="/privacy" className="text-primary hover:underline">Datenschutzerklärung</Link>.</span>
        </label>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-primary text-white py-2 rounded-lg hover:bg-primary-dark disabled:opacity-50"
        >
          {loading ? 'Bitte warten…' : 'Registrieren – 14 Tage kostenlos testen'}
        </button>

        <p className="text-center text-sm text-gray-600">
          Bereits registriert? <Link to="/login" className="text-primary hover:underline">Jetzt einloggen</Link>
        </p>
      </form>
    </div>
  );
}
