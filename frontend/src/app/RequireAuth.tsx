import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { isApiError } from '../api/client';
import type { MeOut, MenuOut } from '../api/types';
import { useAuthFlow } from '../auth/AuthFlow';
import { useMe } from '../auth/api';
import { PasswordChangePage } from '../auth/PasswordChangePage';
import { useMenu } from '../meta/api';
import type { Route } from '../router/hash';
import { navigate } from '../router/store';
import { HomeRedirect } from '../shell/HomeRedirect';
import { SectionScreen } from '../shell/SectionScreen';
import { ShellSkeleton } from '../shell/ShellSkeleton';
import { ShellTools } from '../shell/ShellTools';
import { StatusScreen } from '../shell/StatusScreen';
import { FullPageError } from './FullPageError';
import { endSession } from './queryClient';

/** Himoyalangan marshrutlar: me → (majburiy parol) → menyu → ekran. Tekshiruv baribir serverda. */
export function RequireAuth({ route }: { route: Route }) {
  const me = useMe();
  const client = useQueryClient();
  const flow = useAuthFlow();
  const unauthenticated = isApiError(me.error, 401);
  const mustChange = me.data?.must_change_password ?? false;
  const menu = useMenu(me.isSuccess && !mustChange);

  useEffect(() => {
    if (mustChange && route.kind !== 'password') navigate({ kind: 'password' }, { replace: true });
  }, [mustChange, route.kind]);

  // useMe — silent: global 401 ishlovi ishlamaydi, shuning uchun sessiya tugashini shu yerda yakunlaymiz.
  useEffect(() => {
    if (unauthenticated) endSession(client, flow.clear);
  }, [unauthenticated, client, flow.clear]);

  if (me.isPending) return <ShellSkeleton />;
  if (me.isError) {
    return unauthenticated ? <ShellSkeleton /> : <FullPageError error={me.error} onRetry={() => void me.refetch()} />;
  }
  if (route.kind === 'password') return <PasswordChangePage me={me.data} />;
  if (mustChange || menu.isPending) return <ShellSkeleton />;
  if (menu.isError) return <FullPageError error={menu.error} onRetry={() => void menu.refetch()} />;
  return <Screen me={me.data} menu={menu.data} route={route} />;
}

function Screen({ me, menu, route }: { me: MeOut; menu: MenuOut; route: Route }) {
  const tools = <ShellTools me={me} menu={menu} route={route} />;
  switch (route.kind) {
    case 'home':
      return <HomeRedirect menu={menu} />;
    case 'section':
      return <SectionScreen me={me} menu={menu} route={route} tools={tools} />;
    case 'noaccess':
      return <StatusScreen kind="noaccess" menu={menu} tools={tools} />;
    default:
      return <StatusScreen kind="notfound" menu={menu} tools={tools} />;
  }
}
