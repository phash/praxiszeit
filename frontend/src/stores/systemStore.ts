import { create } from 'zustand';
import apiClient from '../api/client';

export type DeploymentMode = 'saas' | 'onprem';

interface SystemInfo {
  deployment_mode: DeploymentMode;
  version: string;
  beta?: boolean;
  onboarding_enabled?: boolean;
}

interface SystemState {
  info: SystemInfo | null;
  isLoaded: boolean;
  fetch: () => Promise<void>;
  isSaas: () => boolean;
  isOnprem: () => boolean;
  isBeta: () => boolean;
  isOnboardingEnabled: () => boolean;
}

// Conservative default: treat as on-prem until the /api/system/info response
// lands. This prevents SaaS-only UI (public signup, billing links) from
// flickering in on single-tenant installs while hydrate is in flight.
export const useSystemStore = create<SystemState>((set, get) => ({
  info: null,
  isLoaded: false,

  fetch: async () => {
    try {
      const { data } = await apiClient.get<SystemInfo>('/system/info');
      set({ info: data, isLoaded: true });
    } catch {
      set({
        info: { deployment_mode: 'onprem', version: '' },
        isLoaded: true,
      });
    }
  },

  isSaas: () => get().info?.deployment_mode === 'saas',
  isOnprem: () => get().info?.deployment_mode !== 'saas',
  isBeta: () => get().info?.beta === true,
  // Default an: solange /system/info nicht geladen ist ODER das Feld fehlt, wird
  // das Onboarding gezeigt (nur ein explizites false unterdrückt es).
  isOnboardingEnabled: () => get().info?.onboarding_enabled !== false,
}));
