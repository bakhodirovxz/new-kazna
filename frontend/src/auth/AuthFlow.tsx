import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

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
  finish(): void;
  clear(): void;
}

const AuthFlowContext = createContext<AuthFlowValue | null>(null);

export function AuthFlowProvider({ children }: { children: ReactNode }) {
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [returnTo, setReturnTo] = useState<string | null>(null);

  const begin = useCallback((next: Challenge) => {
    setChallenge(next);
    setReturnTo(next.returnTo);
  }, []);
  const finish = useCallback(() => setChallenge(null), []);
  const clear = useCallback(() => {
    setChallenge(null);
    setReturnTo(null);
  }, []);

  const value = useMemo(() => ({ challenge, returnTo, begin, finish, clear }), [challenge, returnTo, begin, finish, clear]);
  return <AuthFlowContext.Provider value={value}>{children}</AuthFlowContext.Provider>;
}

export function useAuthFlow(): AuthFlowValue {
  const context = useContext(AuthFlowContext);
  if (!context) throw new Error('useAuthFlow: AuthFlowProvider topilmadi');
  return context;
}
