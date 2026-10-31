import { useEffect, useState } from 'react';

const COMPACT_QUERY = '(max-width: 1023px)';

/** True below the lg breakpoint, where the three-pane workspace cannot fit. */
export function useCompactLayout() {
  const [compact, setCompact] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia(COMPACT_QUERY).matches : false
  );

  useEffect(() => {
    const media = window.matchMedia(COMPACT_QUERY);
    const onChange = () => setCompact(media.matches);
    onChange();
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  return compact;
}
