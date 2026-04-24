import { useEffect, useState } from 'react';
import { CreditCard, ArrowUpCircle, AlertTriangle } from 'lucide-react';
import apiClient from '../../api/client';
import { getErrorMessage } from '../../utils/errorMessage';

interface BillingInfo {
  id: string;
  plan: 'trial' | 'starter' | 'pro' | 'enterprise';
  subscription_status: 'active' | 'past_due' | 'canceled' | 'suspended';
  trial_ends_at: string | null;
  stripe_customer_id: string | null;
  billing_email: string | null;
  company_name: string | null;
  vat_id: string | null;
  country: string | null;
}

interface Invoice {
  id: string;
  stripe_invoice_id: string;
  amount_cents: number;
  currency: string;
  status: string;
  paid_at: string | null;
  created_at: string;
  hosted_invoice_url: string | null;
}

export default function Billing() {
  const [info, setInfo] = useState<BillingInfo | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    void refresh();
  }, []);

  async function refresh() {
    setLoading(true);
    try {
      const [b, i] = await Promise.all([
        apiClient.get<BillingInfo>('/tenant/billing'),
        apiClient.get<Invoice[]>('/tenant/invoices'),
      ]);
      setInfo(b.data);
      setInvoices(i.data);
    } catch (err: any) {
      setError(getErrorMessage(err, 'Fehler beim Laden der Abrechnung'));
    } finally {
      setLoading(false);
    }
  }

  async function upgrade(plan: 'starter' | 'pro', yearly: boolean) {
    try {
      const { data } = await apiClient.post<{ url: string }>('/billing/checkout', {
        plan,
        yearly,
        success_url: `${window.location.origin}/admin/billing?success=1`,
        cancel_url: `${window.location.origin}/admin/billing?canceled=1`,
      });
      window.location.href = data.url;
    } catch (err: any) {
      setError(getErrorMessage(err, 'Checkout fehlgeschlagen'));
    }
  }

  async function openPortal() {
    try {
      const { data } = await apiClient.post<{ url: string }>('/billing/portal', {
        return_url: `${window.location.origin}/admin/billing`,
      });
      window.location.href = data.url;
    } catch (err: any) {
      setError(getErrorMessage(err, 'Kundenportal nicht erreichbar'));
    }
  }

  if (loading) return <p className="p-6 text-sm text-gray-600">Laden…</p>;
  if (!info) return <p className="p-6 text-sm text-red-600">{error || 'Keine Daten verfügbar.'}</p>;

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <CreditCard className="text-primary" />
        <h1 className="text-2xl font-semibold">Abrechnung</h1>
      </div>

      {info.subscription_status === 'past_due' && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 flex items-start gap-2 text-sm">
          <AlertTriangle className="text-amber-700 mt-0.5" size={18} />
          <div>
            <p className="font-medium text-amber-900">Letzte Zahlung fehlgeschlagen</p>
            <p className="text-amber-800">Bitte aktualisiere deine Zahlungsmethode im Kundenportal.</p>
          </div>
        </div>
      )}

      {info.subscription_status === 'suspended' && (
        <div className="rounded-lg border border-red-300 bg-red-50 p-4 flex items-start gap-2 text-sm">
          <AlertTriangle className="text-red-700 mt-0.5" size={18} />
          <div>
            <p className="font-medium text-red-900">Account gesperrt</p>
            <p className="text-red-800">
              Der Schreibzugriff ist deaktiviert. Bestehende Daten bleiben lesbar und
              exportierbar (§16 ArbZG). Zahlungsmethode aktualisieren, um wieder freizuschalten.
            </p>
          </div>
        </div>
      )}

      <section className="bg-white rounded-xl shadow-card p-6 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-medium">Aktueller Plan</h2>
            <p className="text-2xl font-semibold mt-1 capitalize">{info.plan}</p>
            <p className="text-sm text-gray-600 mt-1">
              Status: <span className="font-medium">{info.subscription_status}</span>
            </p>
            {info.trial_ends_at && info.plan === 'trial' && (
              <p className="text-xs text-gray-500 mt-1">
                Trial endet am {new Date(info.trial_ends_at).toLocaleDateString('de-DE')}
              </p>
            )}
          </div>
          {info.stripe_customer_id && (
            <button
              onClick={openPortal}
              className="px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm"
            >
              Kundenportal
            </button>
          )}
        </div>
      </section>

      {(info.plan === 'trial' || info.plan === 'starter') && (
        <section className="bg-white rounded-xl shadow-card p-6">
          <h2 className="text-lg font-medium mb-4">Upgrade</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {info.plan === 'trial' && (
              <button
                onClick={() => upgrade('starter', false)}
                className="flex items-center gap-2 p-4 border border-gray-200 rounded-lg hover:border-primary hover:bg-primary/5 text-left"
              >
                <ArrowUpCircle size={20} className="text-primary" />
                <div>
                  <p className="font-medium">Starter</p>
                  <p className="text-sm text-gray-500">5 Sitze, monatlich</p>
                </div>
              </button>
            )}
            <button
              onClick={() => upgrade('pro', false)}
              className="flex items-center gap-2 p-4 border border-gray-200 rounded-lg hover:border-primary hover:bg-primary/5 text-left"
            >
              <ArrowUpCircle size={20} className="text-primary" />
              <div>
                <p className="font-medium">Pro</p>
                <p className="text-sm text-gray-500">25 Sitze, monatlich</p>
              </div>
            </button>
          </div>
        </section>
      )}

      <section className="bg-white rounded-xl shadow-card p-6">
        <h2 className="text-lg font-medium mb-4">Rechnungen</h2>
        {invoices.length === 0 ? (
          <p className="text-sm text-gray-500">Noch keine Rechnungen.</p>
        ) : (
          <ul className="divide-y">
            {invoices.map((inv) => (
              <li key={inv.id} className="py-3 flex items-center justify-between text-sm">
                <div>
                  <p>{new Date(inv.created_at).toLocaleDateString('de-DE')}</p>
                  <p className="text-xs text-gray-500">
                    {(inv.amount_cents / 100).toFixed(2)} {inv.currency.toUpperCase()} · {inv.status}
                  </p>
                </div>
                {inv.hosted_invoice_url && (
                  <a
                    href={inv.hosted_invoice_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline"
                  >
                    öffnen
                  </a>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
