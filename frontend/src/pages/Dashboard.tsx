import { useEffect, useState } from 'react';
import apiClient from '../api/client';
import { TrendingUp, TrendingDown, Calendar, Clock } from 'lucide-react';

interface DashboardData {
  year: number;
  month: number;
  target_hours: number;
  actual_hours: number;
  balance: number;
}

interface VacationAccount {
  year: number;
  budget_hours: number;
  budget_days: number;
  used_hours: number;
  used_days: number;
  remaining_hours: number;
  remaining_days: number;
}

interface OvertimeAccount {
  current_balance: number;
}

export default function Dashboard() {
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [overtimeAccount, setOvertimeAccount] = useState<OvertimeAccount | null>(null);
  const [vacationAccount, setVacationAccount] = useState<VacationAccount | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [dashboardRes, overtimeRes, vacationRes] = await Promise.all([
          apiClient.get('/dashboard'),
          apiClient.get('/dashboard/overtime'),
          apiClient.get('/dashboard/vacation'),
        ]);

        setDashboardData(dashboardRes.data);
        setOvertimeAccount(overtimeRes.data);
        setVacationAccount(vacationRes.data);
      } catch (error) {
        console.error('Failed to fetch dashboard data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Lade Dashboard...</div>
      </div>
    );
  }

  const monthNames = [
    'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
  ];

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-8">Dashboard</h1>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        {/* Monthly Balance */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium text-gray-600">Monatssaldo</h3>
            <Calendar className="text-primary" size={24} />
          </div>
          {dashboardData && (
            <>
              <p className="text-xs text-gray-500 mb-2">
                {monthNames[dashboardData.month - 1]} {dashboardData.year}
              </p>
              <p
                className={`text-3xl font-bold ${
                  dashboardData.balance >= 0 ? 'text-green-600' : 'text-red-600'
                }`}
              >
                {dashboardData.balance >= 0 ? '+' : ''}
                {dashboardData.balance.toFixed(2)} h
              </p>
              <div className="mt-4 space-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-600">Soll:</span>
                  <span className="font-medium">{dashboardData.target_hours.toFixed(2)} h</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Ist:</span>
                  <span className="font-medium">{dashboardData.actual_hours.toFixed(2)} h</span>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Overtime Account */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium text-gray-600">Überstundenkonto</h3>
            {overtimeAccount && overtimeAccount.current_balance >= 0 ? (
              <TrendingUp className="text-green-600" size={24} />
            ) : (
              <TrendingDown className="text-red-600" size={24} />
            )}
          </div>
          {overtimeAccount && (
            <>
              <p className="text-xs text-gray-500 mb-2">Kumulierter Saldo</p>
              <p
                className={`text-3xl font-bold ${
                  overtimeAccount.current_balance >= 0 ? 'text-green-600' : 'text-red-600'
                }`}
              >
                {overtimeAccount.current_balance >= 0 ? '+' : ''}
                {overtimeAccount.current_balance.toFixed(2)} h
              </p>
            </>
          )}
        </div>

        {/* Vacation Account */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium text-gray-600">Urlaubskonto</h3>
            <Clock className="text-primary" size={24} />
          </div>
          {vacationAccount && (
            <>
              <p className="text-xs text-gray-500 mb-2">Resturlaub {vacationAccount.year}</p>
              <p className="text-3xl font-bold text-primary">
                {vacationAccount.remaining_days.toFixed(1)} Tage
              </p>
              <div className="mt-4 space-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-600">Budget:</span>
                  <span className="font-medium">{vacationAccount.budget_days} Tage</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Genommen:</span>
                  <span className="font-medium">{vacationAccount.used_days.toFixed(1)} Tage</span>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Quick Info */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-6">
        <h3 className="text-lg font-semibold text-blue-900 mb-2">Willkommen bei PraxisZeit</h3>
        <p className="text-blue-700">
          Nutzen Sie die Navigation links, um Ihre Zeiteinträge zu verwalten, Abwesenheiten einzutragen
          oder Ihre Übersicht anzusehen.
        </p>
      </div>
    </div>
  );
}
