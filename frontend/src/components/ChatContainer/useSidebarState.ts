import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import { logger } from '@/utils/logger';

const MOBILE_QUERY = '(max-width: 768px)';
const subscribe = (listener: () => void) => {
  const query = window.matchMedia(MOBILE_QUERY);
  query.addEventListener('change', listener);
  return () => query.removeEventListener('change', listener);
};
const getSnapshot = () => window.matchMedia(MOBILE_QUERY).matches;
const getServerSnapshot = () => false;

/**
 * Keep desktop collapse and mobile drawer preferences independent.
 *
 * Returns:
 *   Viewport-aware visibility, CSS state flags and stable navigation actions.
 * Side effects:
 *   Subscribes to the CSS breakpoint. Debug logs contain only viewport mode
 *   and visibility. Both state flags have responsive CSS defaults, preserving
 *   the correct first-paint layout before the client knows the viewport.
 */
export function useSidebarState() {
  const isMobile = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const [desktopCollapsed, setDesktopCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const isOpen = isMobile ? mobileOpen : !desktopCollapsed;
  const toggle = useCallback(() => {
    if (isMobile) setMobileOpen(value => !value);
    else setDesktopCollapsed(value => !value);
  }, [isMobile]);
  const collapseDesktop = useCallback(() => setDesktopCollapsed(true), []);
  const closeMobile = useCallback(() => setMobileOpen(false), []);

  useEffect(() => {
    logger.debug('sidebar_visibility_changed', { viewport: isMobile ? 'mobile' : 'desktop', expanded: isOpen });
  }, [isMobile, isOpen]);

  return { isMobile, isOpen, desktopCollapsed, mobileOpen, toggle, collapseDesktop, closeMobile };
}
