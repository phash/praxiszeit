import { useState, useCallback, useRef } from 'react';

interface ConfirmState {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  variant?: 'danger' | 'warning' | 'info';
  onConfirm: () => void | Promise<void>;
}

const initialState: ConfirmState = {
  isOpen: false,
  title: '',
  message: '',
  onConfirm: () => {},
};

export function useConfirm() {
  const [state, setState] = useState<ConfirmState>(initialState);

  const confirm = useCallback(
    (options: {
      title: string;
      message: string;
      confirmLabel?: string;
      variant?: 'danger' | 'warning' | 'info';
      onConfirm: () => void | Promise<void>;
    }) => {
      setState({ isOpen: true, ...options });
    },
    []
  );

  // zeit-08: Doppelklick-Schutz — der Dialog schließt sofort, ein zweiter Klick
  // auf dieselbe Bestätigung (solange die Aktion läuft) wird verworfen.
  const busy = useRef(false);
  const handleConfirm = useCallback(() => {
    if (busy.current) return;
    busy.current = true;
    const action = state.onConfirm;
    setState(initialState);
    Promise.resolve()
      .then(() => action())
      .catch(() => {})
      .finally(() => {
        busy.current = false;
      });
  }, [state]);

  const handleCancel = useCallback(() => {
    setState(initialState);
  }, []);

  return {
    confirmState: state,
    confirm,
    handleConfirm,
    handleCancel,
  };
}
