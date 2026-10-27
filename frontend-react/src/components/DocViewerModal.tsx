import React, { useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { X } from 'lucide-react';

export interface DemoDocData {
  title: string;
  filename: string;
  desc: string;
  pages: number;
  chunks: number;
  category: string;
  pdfUrl: string;
}

interface DocViewerModalProps {
  doc: DemoDocData | null;
  onClose: () => void;
}

export const DocViewerModal: React.FC<DocViewerModalProps> = ({ doc, onClose }) => {
  // Listen for Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  if (!doc) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 select-none">
        {/* Backdrop */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="fixed inset-0 bg-black/70 backdrop-blur-xs transition-opacity"
        />

        {/* Modal Window: Only the PDF Preview */}
        <motion.div
          initial={{ opacity: 0, scale: 0.97, y: 8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.97, y: 8 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
          className="relative w-full max-w-4xl h-[90vh] bg-card border border-border rounded-xl shadow-2xl flex flex-col z-10 overflow-hidden"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Floating Close Button */}
          <button
            type="button"
            onClick={onClose}
            className="absolute top-3 right-3 z-20 size-8 rounded-full bg-background/90 hover:bg-background border border-border shadow-md text-foreground flex items-center justify-center transition-all cursor-pointer hover:scale-105"
            title="Close"
          >
            <X className="size-4" />
          </button>

          {/* Only the PDF section */}
          <div className="flex-1 w-full h-full bg-muted/20 overflow-hidden">
            <iframe
              src={doc.pdfUrl}
              title={doc.title}
              className="w-full h-full border-none"
            />
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};
