import { useState } from 'react';
import { useAuthStore } from '../stores/authStore';
import apiClient from '../api/client';
import { Lock, Save, Palette } from 'lucide-react';

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
  const [passwordData, setPasswordData] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  });
  const [selectedColor, setSelectedColor] = useState(user?.calendar_color || '#93C5FD');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [colorMessage, setColorMessage] = useState('');

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage('');
    setError('');

    if (passwordData.new_password !== passwordData.confirm_password) {
      setError('Passwörter stimmen nicht überein');
      return;
    }

    if (passwordData.new_password.length < 8) {
      setError('Passwort muss mindestens 8 Zeichen lang sein');
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

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-8">Profil</h1>

      {/* User Info */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
        <div className="flex items-center space-x-4 mb-6">
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
              <input
                type="password"
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
              <input
                type="password"
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
              <input
                type="password"
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
