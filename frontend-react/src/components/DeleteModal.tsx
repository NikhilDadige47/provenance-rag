import React from 'react';
import { AlertTriangle, Trash2 } from 'lucide-react';
import { Button } from './ui/button';

interface DeleteModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  isDeleting: boolean;
}

export const DeleteModal: React.FC<DeleteModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  isDeleting,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm animate-in fade-in-0 duration-200">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-lg space-y-4">
        <div className="flex items-center gap-3 text-destructive">
          <div className="size-10 rounded-full bg-destructive/10 flex items-center justify-center">
            <AlertTriangle className="size-5" />
          </div>
          <div>
            <h3 className="font-semibold text-base text-foreground">Wipe Session Documents</h3>
            <p className="text-xs text-muted-foreground">This action cannot be undone.</p>
          </div>
        </div>

        <p className="text-xs text-muted-foreground leading-relaxed">
          Deleting your session will immediately purge all uploaded PDF files from disk, remove all vector points from Qdrant, clear sparse BM25 indices, and revoke your session token.
        </p>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" size="sm" onClick={onClose} disabled={isDeleting}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={onConfirm}
            disabled={isDeleting}
            className="gap-1.5"
          >
            <Trash2 className="size-3.5" />
            <span>{isDeleting ? 'Wiping...' : 'Confirm Wipe'}</span>
          </Button>
        </div>
      </div>
    </div>
  );
};
