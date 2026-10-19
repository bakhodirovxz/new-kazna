import { QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { AuthFlowProvider, useAuthFlow } from '../auth/AuthFlow';
import { ToastProvider, useToast } from '../ui/Toast';
import { makeQueryClient } from './queryClient';
import { Routes } from './Routes';

function ClientBoundary({ children }: { children: ReactNode }) {
  const toast = useToast();
  const flow = useAuthFlow();
  const [client] = useState(() => makeQueryClient((message) => toast.show(message, 'error'), flow.clear));
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

// AuthFlowProvider ClientBoundary'dan tashqarida: 401 AuthFlow'ni ham tozalashi kerak (flow.clear barqaror).
export function App() {
  return (
    <ToastProvider>
      <AuthFlowProvider>
        <ClientBoundary>
          <Routes />
        </ClientBoundary>
      </AuthFlowProvider>
    </ToastProvider>
  );
}
