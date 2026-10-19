import { createContext, useContext, useMemo, useState, useSyncExternalStore, type ReactNode } from 'react';

/** Login → 2FA oralig'idagi holat. mfa_token faqat xotirada: sahifa yangilansa — login qaytadan. */
export interface Challenge {
  mfaToken: string;
  step: 'mfa_verify' | 'mfa_enroll';
  username: string;
  returnTo: string | null;
}

interface AuthFlowValue {
  challenge: Challenge | null;
  /** 2FA'dan keyin (masalan, majburiy parol almashtirishdan so'ng) qaytiladigan joy. */
  returnTo: string | null;
  begin(challenge: Challenge): void;
  /** Majburiy parol almashtirishdan keyin qaytiladigan joyni eslab qoladi (bor bo'lsa — almashtirmaydi). */
  remember(path: string | null): void;
  finish(): void;
  clear(): void;
}

interface FlowState {
  challenge: Challenge | null;
  returnTo: string | null;
}

interface FlowStore {
  subscribe(listener: () => void): () => void;
  getState(): FlowState;
  actions: Pick<AuthFlowValue, 'begin' | 'remember' | 'finish' | 'clear'>;
}

/** Tashqi store: begin/clear router `navigate` bilan bir tikda sinxron ko'rinadi (React setState emas —
 *  u router'dan keyin commit bo'lib, 2FA sahifasi challenge'siz render bo'lardi). */
function createFlowStore(): FlowStore {
  let state: FlowState = { challenge: null, returnTo: null };
  const listeners = new Set<() => void>();
  const set = (next: FlowState) => {
    if (next.challenge === state.challenge && next.returnTo === state.returnTo) return;
    state = next;
    listeners.forEach((listener) => listener());
  };
  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    getState: () => state,
    actions: {
      begin: (challenge) => set({ challenge, returnTo: challenge.returnTo }),
      remember: (path) => set({ ...state, returnTo: state.returnTo ?? path }),
      finish: () => set({ ...state, challenge: null }),
      clear: () => set({ challenge: null, returnTo: null }),
    },
  };
}

const AuthFlowContext = createContext<FlowStore | null>(null);

export function AuthFlowProvider({ children }: { children: ReactNode }) {
  const [store] = useState(createFlowStore);
  return <AuthFlowContext.Provider value={store}>{children}</AuthFlowContext.Provider>;
}

export function useAuthFlow(): AuthFlowValue {
  const store = useContext(AuthFlowContext);
  if (!store) throw new Error('useAuthFlow: AuthFlowProvider topilmadi');
  const state = useSyncExternalStore(store.subscribe, store.getState, store.getState);
  return useMemo(() => ({ ...state, ...store.actions }), [state, store]);
}
