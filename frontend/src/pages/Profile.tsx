import { useState } from 'react';
import { useAuthStore } from '../stores/authStore';
import apiClient from '../api/client';
import { Lock, Save, Palette, User as UserIcon, Download, ShieldCheck, ShieldOff, Smartphone, Copy, CheckCircle } from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';
import PasswordInput from '../components/PasswordInput';

// 12 beautiful pastel colors for calendar
const PASTEL_COLORS = [
  { name: 'Blau', hex: '#93C5FD' },
  { name: 'Rosa', hex: '#F9A8D4' },
  { name: 'Lila', hex: '#DDD6FE' },
  { name: 'Grün', hex: '#86EFAC' },
  { name: 'Gelb', hex: '#FDE047' },
  { name: 'Orange', hex: '#FDBA74' },
  { name: 'Türkis', hex: '#5EEAD4' },
  { name: 'Mint', hex: '#A7F3D0' },
  { name: 'Pfirsich', hex: '#FED7AA' },
  { name: 'Lavendel', hex: '#E9D5FF' },
  { name: 'Hellblau', hex: '#BAE6FD' },
  { name: 'Koralle', hex: '#FCA5A5' },
];

export default function Profile() {
  const { user, setUser } = useAuthStore();
  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [showProfileEdit, setShowProfileEdit] = useState(false);
  const [profileData, setProfileData] = useState({
    first_name: user?.first_name || '',
    last_name: user?.last_name || '',
    email: user?.email || '',
  });
  const [passwordData, setPasswordData] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  });
  const [selectedColor, setSelectedColor] = useState(user?.calendar_color || '#93C5FD');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [colorMessage, setColorMessage] = useState('');
  const [profileMessage, setProfileMessage] = useState('');

  // F-019: TOTP 2FA state
  const [totpEnabled, setTotpEnabled] = useState(user?.totp_enabled ?? false);
  const [showTotpSetup, setShowTotpSetup] = useState(false);
  const [totpSetupData, setTotpSetupData] = useState<{ otpauth_uri: string; secret: string } | null>(null);
  const [totpVerifyCode, setTotpVerifyCode] = useState('');
  const [showTotpDisable, setShowTotpDisable] = useState(false);
  const [totpDisablePassword, setTotpDisablePassword] = useState('');
  const [totpMessage, setTotpMessage] = useState('');
  const [totpError, setTotpError] = useState('');
  const [secretCopied, setSecretCopied] = useState(false);

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage('');
    setError('');

    if (passwordData.new_password !== passwordData.confirm_password) {
      setError('Passwörter stimmen nicht überein');
      return;
    }

    if (passwordData.new_password.length < 10) {
      setError('Passwort muss mindestens 10 Zeichen lang sein');
      return;
    }
    if (!/[A-Z]/.test(passwordData.new_password)) {
      setError('Passwort muss mindestens einen Großbuchstaben enthalten');
      return;
    }
    if (!/[a-z]/.test(passwordData.new_password)) {
      setError('Passwort muss mindestens einen Kleinbuchstaben enthalten');
      return;
    }
    if (!/[0-9]/.test(passwordData.new_password)) {
      setError('Passwort muss mindestens eine Ziffer enthalten');
      return;
    }

    try {
      await apiClient.post('/auth/change-password', {
        current_password: passwordData.current_password,
        new_password: passwordData.new_password,
      });
      setMessage('Passwort erfolgreich geändert');
      setPasswordData({ current_password: '', new_password: '', confirm_password: '' });
      setShowPasswordForm(false);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Ändern des Passworts');
    }
  };

  const handleProfileUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileMessage('');
    try {
      const response = await apiClient.put('/auth/profile', {
        first_name: profileData.first_name || undefined,
        last_name: profileData.last_name || undefined,
        email: profileData.email,
      });
      setUser(response.data);
      setProfileMessage('Daten erfolgreich aktualisiert');
      setShowProfileEdit(false);
      setTimeout(() => setProfileMessage(''), 4000);
    } catch (err: any) {
      setProfileMessage(err.response?.data?.detail || 'Fehler beim Speichern');
    }
  };

  const handleDataExport = async () => {
    try {
      const response = await apiClient.get('/auth/me/export', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/json' }));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `PraxisZeit_Datenauszug_${user?.username}.json`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch {
      // silent
    }
  };

  const handleColorChange = async (color: string) => {
    setSelectedColor(color);
    setColorMessage('');

    try {
      const response = await apiClient.put('/auth/calendar-color', {
        calendar_color: color,
      });
      setUser(response.data);
      setColorMessage('Kalenderfarbe erfolgreich aktualisiert');
      setTimeout(() => setColorMessage(''), 3000);
    } catch (err: any) {
      setColorMessage('Fehler beim Speichern der Farbe');
    }
  };

  // ── F-019: TOTP handlers ──────────────────────────────────────────────────

  const handleTotpSetup = async () => {
    setTotpError('');
    setTotpMessage('');
    try {
      const response = await apiClient.post('/auth/totp/setup');
      setTotpSetupData(response.data);
      setShowTotpSetup(true);
    } catch (err: any) {
      setTotpError(err.response?.data?.detail || 'Fehler beim Starten der 2FA-Einrichtung');
    }
  };

  const handleTotpVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setTotpError('');
    try {
      const response = await apiClient.post('/auth/totp/verify', { code: totpVerifyCode });
      setUser(response.data);
      setTotpEnabled(true);
      setShowTotpSetup(false);
      setTotpSetupData(null);
      setTotpVerifyCode('');
      setTotpMessage('2FA wurde erfolgreich aktiviert.');
      setTimeout(() => setTotpMessage(''), 5000);
    } catch (err: any) {
      setTotpError(err.response?.data?.detail || 'Ungültiger Code. Bitte erneut versuchen.');
      setTotpVerifyCode('');
    }
  };

  const handleTotpDisable = async (e: React.FormEvent) => {
    e.preventDefault();
    setTotpError('');
    try {
      const response = await apiClient.delete('/auth/totp/disable', {
        data: { password: totpDisablePassword },
      });
      setUser(response.data);
      setTotpEnabled(false);
      setShowTotpDisable(false);
      setTotpDisablePassword('');
      setTotpMessage('2FA wurde deaktiviert.');
      setTimeout(() => setTotpMessage(''), 5000);
    } catch (err: any) {
      setTotpError(err.response?.data?.detail || 'Fehler beim Deaktivieren der 2FA');
    }
  };

  const handleCopySecret = () => {
    if (totpSetupData?.secret) {
      navigator.clipboard.writeText(totpSetupData.secret);
      setSecretCopied(true);
      setTimeout(() => setSecretCopied(false), 2000);
    }
  };

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-8">Profil</h1>

      {/* User Info */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
        <div className="flex items-start justify-between mb-6">
          <div className="flex items-center space-x-4">
            <div className="w-20 h-20 rounded-full bg-primary text-white flex items-center justify-center text-2xl font-bold">
              {user?.first_name[0]}
              {user?.last_name[0]}
            </div>
            <div>
              <h2 className="text-2xl font-semibold text-gray-900">
                {user?.first_name} {user?.last_name}
              </h2>
              <p className="text-gray-600">{user?.username}</p>
              {user?.email && (
                <p className="text-gray-500 text-sm">{user.email}</p>
              )}
            </div>
          </div>
          <button
            onClick={() => { setShowProfileEdit(!showProfileEdit); setProfileMessage(''); }}
            className="flex items-center space-x-1 text-sm text-primary hover:text-primary-dark font-medium"
          >
            <UserIcon size={15} />
            <span>{showProfileEdit ? 'Abbrechen' : 'Bearbeiten'}</span>
          </button>
        </div>

        {profileMessage && (
          <div className={`mb-4 px-4 py-3 rounded-lg text-sm border ${profileMessage.includes('Fehler') ? 'bg-red-50 border-red-200 text-red-700' : 'bg-green-50 border-green-200 text-green-700'}`}>
            {profileMessage}
          </div>
        )}

        {showProfileEdit ? (
          <form onSubmit={handleProfileUpdate} className="space-y-4 mb-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Vorname</label>
                <input
                  type="text"
                  value={profileData.first_name}
                  onChange={e => setProfileData(p => ({ ...p, first_name: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Nachname</label>
                <input
                  type="text"
                  value={profileData.last_name}
                  onChange={e => setProfileData(p => ({ ...p, last_name: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                />
              </div>
              <div className="md:col-span-2">
                <label className="block text-sm font-medium text-gray-700 mb-1">E-Mail (optional)</label>
                <input
                  type="email"
                  value={profileData.email}
                  onChange={e => setProfileData(p => ({ ...p, email: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                  placeholder="beispiel@praxis.de"
                />
              </div>
            </div>
            <button
              type="submit"
              className="flex items-center space-x-2 bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg transition text-sm"
            >
              <Save size={16} />
              <span>Speichern</span>
            </button>
          </form>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-gray-500">Rolle</label>
              <p className="text-gray-900 mt-1">
                {user?.role === 'admin' ? 'Administrator' : 'Mitarbeiter:in'}
              </p>
            </div>
            <div>
              <label className="text-sm font-medium text-gray-500">Wochenstunden</label>
              <p className="text-gray-900 mt-1">{user?.weekly_hours} Stunden</p>
            </div>
            <div>
              <label className="text-sm font-medium text-gray-500">Urlaubstage</label>
              <p className="text-gray-900 mt-1">{user?.vacation_days} Tage</p>
            </div>
            <div>
              <label className="text-sm font-medium text-gray-500">Status</label>
              <p className="text-gray-900 mt-1">
                {user?.is_active ? (
                  <span className="text-green-600">Aktiv</span>
                ) : (
                  <span className="text-red-600">Inaktiv</span>
                )}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* DSGVO: Datenauszug (Art. 20) */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold flex items-center space-x-2">
              <Download size={20} />
              <span>Meine Daten exportieren</span>
            </h3>
            <p className="text-sm text-gray-600 mt-1">
              Laden Sie alle zu Ihrer Person gespeicherten Daten herunter (Art. 20 DSGVO – Datenportabilität).
            </p>
          </div>
          <button
            onClick={handleDataExport}
            className="flex items-center space-x-2 bg-gray-100 hover:bg-gray-200 text-gray-700 px-4 py-2 rounded-lg transition text-sm font-medium"
          >
            <Download size={16} />
            <span>JSON herunterladen</span>
          </button>
        </div>
      </div>

      {/* F-019: Zwei-Faktor-Authentifizierung */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
        <div className="flex items-center space-x-2 mb-1">
          <Smartphone size={20} />
          <h3 className="text-lg font-semibold">Zwei-Faktor-Authentifizierung (2FA)</h3>
        </div>
        <p className="text-sm text-gray-600 mb-4">
          Schützen Sie Ihr Konto mit einem zusätzlichen Einmal-Code aus einer Authenticator-App (z. B. Google Authenticator, Authy).
        </p>

        {totpMessage && (
          <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg text-sm mb-4 flex items-center gap-2">
            <CheckCircle size={16} />
            {totpMessage}
          </div>
        )}
        {totpError && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm mb-4">
            {totpError}
          </div>
        )}

        {/* Status badge */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            {totpEnabled ? (
              <>
                <ShieldCheck size={18} className="text-green-600" />
                <span className="text-sm font-medium text-green-700 bg-green-50 px-2 py-0.5 rounded-full border border-green-200">
                  Aktiviert
                </span>
              </>
            ) : (
              <>
                <ShieldOff size={18} className="text-gray-400" />
                <span className="text-sm font-medium text-gray-500 bg-gray-50 px-2 py-0.5 rounded-full border border-gray-200">
                  Deaktiviert
                </span>
              </>
            )}
          </div>

          {!totpEnabled && !showTotpSetup && (
            <button
              onClick={handleTotpSetup}
              className="flex items-center gap-1.5 bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg transition text-sm font-medium"
            >
              <ShieldCheck size={15} />
              2FA aktivieren
            </button>
          )}
          {totpEnabled && !showTotpDisable && (
            <button
              onClick={() => { setShowTotpDisable(true); setTotpError(''); }}
              className="flex items-center gap-1.5 bg-red-50 hover:bg-red-100 text-red-700 px-4 py-2 rounded-lg transition text-sm font-medium border border-red-200"
            >
              <ShieldOff size={15} />
              2FA deaktivieren
            </button>
          )}
        </div>

        {/* Setup wizard */}
        {showTotpSetup && totpSetupData && (
          <div className="border border-blue-200 bg-blue-50 rounded-xl p-5 space-y-4">
            <p className="text-sm font-medium text-blue-800">
              Schritt 1: Scannen Sie den QR-Code mit Ihrer Authenticator-App
            </p>
            <div className="flex justify-center">
              <div className="bg-white p-3 rounded-lg shadow-sm inline-block">
                <QRCodeSVG value={totpSetupData.otpauth_uri} size={180} />
              </div>
            </div>
            <div>
              <p className="text-xs font-medium text-blue-700 mb-1">
                Oder tragen Sie den Schlüssel manuell ein:
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 text-xs bg-white border border-blue-200 rounded px-3 py-2 font-mono tracking-wider break-all">
                  {totpSetupData.secret}
                </code>
                <button
                  type="button"
                  onClick={handleCopySecret}
                  className="flex-shrink-0 p-2 bg-white border border-blue-200 rounded-lg hover:bg-blue-50 transition"
                  title="Kopieren"
                >
                  {secretCopied ? <CheckCircle size={16} className="text-green-600" /> : <Copy size={16} className="text-blue-600" />}
                </button>
              </div>
            </div>

            <form onSubmit={handleTotpVerify} className="space-y-3 pt-2 border-t border-blue-200">
              <p className="text-sm font-medium text-blue-800">
                Schritt 2: Geben Sie den 6-stelligen Code aus der App ein
              </p>
              <input
                type="text"
                inputMode="numeric"
                pattern="\d{6}"
                maxLength={6}
                value={totpVerifyCode}
                onChange={(e) => setTotpVerifyCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                required
                autoFocus
                className="w-full px-4 py-3 border border-blue-300 rounded-lg focus:ring-2 focus:ring-primary text-center text-xl tracking-widest font-mono"
                placeholder="000000"
              />
              <div className="flex gap-3">
                <button
                  type="submit"
                  disabled={totpVerifyCode.length !== 6}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg transition text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Bestätigen & 2FA aktivieren
                </button>
                <button
                  type="button"
                  onClick={() => { setShowTotpSetup(false); setTotpSetupData(null); setTotpVerifyCode(''); setTotpError(''); }}
                  className="flex-1 bg-white border border-gray-300 text-gray-700 px-4 py-2 rounded-lg transition text-sm hover:bg-gray-50"
                >
                  Abbrechen
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Disable form */}
        {showTotpDisable && (
          <div className="border border-red-200 bg-red-50 rounded-xl p-5 space-y-3">
            <p className="text-sm font-medium text-red-800">
              Bitte bestätigen Sie Ihr Passwort, um 2FA zu deaktivieren:
            </p>
            <form onSubmit={handleTotpDisable} className="space-y-3">
              <PasswordInput
                value={totpDisablePassword}
                onChange={(e) => setTotpDisablePassword(e.target.value)}
                required
                placeholder="Ihr aktuelles Passwort"
                className="w-full px-3 py-2 border border-red-300 rounded-lg focus:ring-2 focus:ring-red-400"
              />
              <div className="flex gap-3">
                <button
                  type="submit"
                  disabled={!totpDisablePassword}
                  className="flex-1 bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg transition text-sm font-medium disabled:opacity-50"
                >
                  2FA deaktivieren
                </button>
                <button
                  type="button"
                  onClick={() => { setShowTotpDisable(false); setTotpDisablePassword(''); setTotpError(''); }}
                  className="flex-1 bg-white border border-gray-300 text-gray-700 px-4 py-2 rounded-lg transition text-sm hover:bg-gray-50"
                >
                  Abbrechen
                </button>
              </div>
            </form>
          </div>
        )}
      </div>

      {/* Calendar Color Selection */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
        <div className="flex items-center space-x-2 mb-4">
          <Palette size={20} />
          <h3 className="text-lg font-semibold">Kalenderfarbe</h3>
        </div>
        <p className="text-sm text-gray-600 mb-4">
          Wählen Sie eine Farbe für Ihre Einträge im Team-Kalender
        </p>

        {colorMessage && (
          <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg text-sm mb-4">
            {colorMessage}
          </div>
        )}

        {/* Color Preview */}
        <div className="flex items-center space-x-3 mb-4">
          <div
            className="w-12 h-12 rounded-lg border-2 border-gray-300"
            style={{ backgroundColor: selectedColor }}
          ></div>
          <div>
            <p className="text-sm font-medium text-gray-700">Gewählte Farbe</p>
            <p className="text-xs text-gray-500">{selectedColor}</p>
          </div>
        </div>

        {/* Color Palette */}
        <div className="grid grid-cols-6 gap-3">
          {PASTEL_COLORS.map((color) => (
            <button
              key={color.hex}
              onClick={() => handleColorChange(color.hex)}
              className={`relative w-full aspect-square rounded-lg transition-all hover:scale-110 ${
                selectedColor === color.hex
                  ? 'ring-4 ring-primary ring-offset-2 scale-110'
                  : 'hover:ring-2 hover:ring-gray-300'
              }`}
              style={{ backgroundColor: color.hex }}
              title={color.name}
            >
              {selectedColor === color.hex && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="w-4 h-4 bg-white rounded-full flex items-center justify-center">
                    <div className="w-2 h-2 bg-primary rounded-full"></div>
                  </div>
                </div>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Password Change */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold flex items-center space-x-2">
            <Lock size={20} />
            <span>Passwort ändern</span>
          </h3>
          {!showPasswordForm && (
            <button
              onClick={() => setShowPasswordForm(true)}
              className="text-primary hover:text-primary-dark text-sm font-medium"
            >
              Ändern
            </button>
          )}
        </div>

        {showPasswordForm && (
          <form onSubmit={handlePasswordChange} className="space-y-4">
            {message && (
              <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg text-sm">
                {message}
              </div>
            )}
            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                {error}
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Aktuelles Passwort
              </label>
              <PasswordInput
                value={passwordData.current_password}
                onChange={(e) =>
                  setPasswordData({ ...passwordData, current_password: e.target.value })
                }
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Neues Passwort</label>
              <PasswordInput
                value={passwordData.new_password}
                onChange={(e) => setPasswordData({ ...passwordData, new_password: e.target.value })}
                required
                minLength={8}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Passwort bestätigen
              </label>
              <PasswordInput
                value={passwordData.confirm_password}
                onChange={(e) =>
                  setPasswordData({ ...passwordData, confirm_password: e.target.value })
                }
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
            </div>

            <div className="flex space-x-3">
              <button
                type="submit"
                className="flex-1 bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center justify-center space-x-2 transition"
              >
                <Save size={18} />
                <span>Speichern</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowPasswordForm(false);
                  setPasswordData({ current_password: '', new_password: '', confirm_password: '' });
                  setError('');
                }}
                className="flex-1 bg-gray-200 hover:bg-gray-300 text-gray-700 px-4 py-2 rounded-lg transition"
              >
                Abbrechen
              </button>
            </div>
          </form>
        )}

        {!showPasswordForm && (
          <p className="text-sm text-gray-500">
            Ihr Passwort sollte mindestens 8 Zeichen lang sein.
          </p>
        )}
      </div>
    </div>
  );
}
