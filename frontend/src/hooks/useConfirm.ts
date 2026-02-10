import { useState, useCallback } from 'react';

interface ConfirmState {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  variant?: 'danger' | 'warning' | 'info';
  onConfirm: () => void;
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
      onConfirm: () => void;
    }) => {
      setState({ isOpen: true, ...options });
    },
    []
  );

  const handleConfirm = useCallback(() => {
    state.onConfirm();
    setState(initialState);
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
