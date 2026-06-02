import { useState, useRef } from 'react';
import ConfirmDialog from '../components/ConfirmDialog';

interface ConfirmOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  danger?: boolean;
  action: () => Promise<void>;
}

/**
 * Hook for managing a confirm dialog with a pending action.
 *
 * Guards against double-click by tracking an in-flight flag.
 * The `confirming` state is exposed so callers can disable
 * the trigger button while the action is running.
 *
 * Usage:
 *   const { confirm, dialog, confirming } = useConfirmDialog();
 *   const handleDelete = () => confirm({
 *     title: 'Delete Item',
 *     message: 'Are you sure?',
 *     action: async () => { await deleteThing(id); },
 *   });
 *   return (<div>{dialog}<button onClick={handleDelete} disabled={confirming}>Delete</button></div>);
 */
export function useConfirmDialog() {
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  const [confirming, setConfirming] = useState(false);
  const confirmingRef = useRef(false);

  const confirm = (opts: ConfirmOptions) => {
    setOptions(opts);
  };

  const handleConfirm = async () => {
    if (!options || confirmingRef.current) return;
    confirmingRef.current = true;
    setConfirming(true);
    try {
      await options.action();
    } finally {
      confirmingRef.current = false;
      setConfirming(false);
      setOptions(null);
    }
  };

  const handleCancel = () => {
    if (confirmingRef.current) return;
    setOptions(null);
  };

  const dialog = options ? (
    <ConfirmDialog
      open={true}
      title={options.title}
      message={options.message}
      confirmLabel={options.confirmLabel}
      danger={options.danger}
      confirming={confirming}
      onConfirm={handleConfirm}
      onCancel={handleCancel}
    />
  ) : null;

  return { confirm, dialog, confirming };
}
