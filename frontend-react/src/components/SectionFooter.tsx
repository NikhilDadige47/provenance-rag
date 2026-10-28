import React from 'react';

/** Shared bottom rail — one strip, top border only. */
export const SECTION_FOOTER_CLASS =
  'h-6 px-2.5 border-t border-border border-x-0 border-b-0 surface-footer shrink-0 flex items-center';

export const SectionFooter: React.FC<{
  children?: React.ReactNode;
  className?: string;
}> = ({ children, className = '' }) => {
  return (
    <div data-section-footer="true" className={`${SECTION_FOOTER_CLASS} ${className}`.trim()}>
      {children}
    </div>
  );
};
