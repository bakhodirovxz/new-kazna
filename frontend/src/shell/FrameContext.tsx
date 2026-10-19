import { createContext, useContext } from 'react';

export interface FrameState {
  isMobile: boolean;
  isTablet: boolean;
  hasSide: boolean;
  sideVisible: boolean;
  toggleSide(): void;
}

export const FrameContext = createContext<FrameState>({
  isMobile: false,
  isTablet: false,
  hasSide: false,
  sideVisible: false,
  toggleSide: () => undefined,
});

export function useFrame(): FrameState {
  return useContext(FrameContext);
}
