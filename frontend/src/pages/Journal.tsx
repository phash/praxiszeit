import { useAuthStore } from '../stores/authStore';
import MonthlyJournal from '../components/MonthlyJournal';

export default function Journal() {
  const user = useAuthStore((s) => s.user);

  if (!user) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Mein Journal</h1>
        <p className="text-sm text-gray-500">Zeiteinträge und Abwesenheiten im Überblick</p>
      </div>
      <MonthlyJournal userId={user.id} isAdminView={false} />
    </div>
  );
}
