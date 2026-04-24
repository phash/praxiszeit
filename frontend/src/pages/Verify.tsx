import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { CheckCircle2, XCircle } from 'lucide-react';
import apiClient from '../api/client';
import { getErrorMessage } from '../utils/errorMessage';

/**
 * /verify?token=… — Confirms the signup link sent to the admin's inbox.
 * Consumes the token on mount and then shows success / failure.
 */
export default function Verify() {
  const [params] = useSearchParams();
  const token = params.get('token');
  const [state, setState] = useState<'loading' | 'ok' | 'error'>('loading');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!token) {
      setState('error');
      setError('Der Bestätigungslink ist unvollständig.');
      return;
    }
    apiClient
      .get(`/public/verify-email?token=${encodeURIComponent(token)}`)
      .then(() => setState('ok'))
      .catch((err) => {
        setState('error');
        setError(getErrorMessage(err, 'Bestätigung fehlgeschlagen.'));
      });
  }, [token]);

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-gray-50">
      <div className="max-w-md w-full bg-white rounded-xl shadow-card p-8 text-center">
        {state === 'loading' && (
          <p className="text-sm text-gray-600">Bestätige deine E-Mail-Adresse…</p>
        )}
        {state === 'ok' && (
          <>
            <CheckCircle2 className="text-success mx-auto mb-4" size={48} />
            <h1 className="text-xl font-semibold mb-2">E-Mail bestätigt</h1>
            <p className="text-sm text-gray-600 mb-4">
              Dein Konto ist aktiviert. Du kannst dich jetzt einloggen.
            </p>
            <Link
              to="/login"
              className="inline-block bg-primary text-white px-4 py-2 rounded-lg hover:bg-primary-dark"
            >
              Zum Login
            </Link>
          </>
        )}
        {state === 'error' && (
          <>
            <XCircle className="text-red-500 mx-auto mb-4" size={48} />
            <h1 className="text-xl font-semibold mb-2">Bestätigung fehlgeschlagen</h1>
            <p className="text-sm text-gray-600 mb-4">{error}</p>
            <Link to="/login" className="text-primary hover:underline">Zurück zum Login</Link>
          </>
        )}
      </div>
    </div>
  );
}
