import { Stack } from 'expo-router';

import { AuthProvider, useAuth } from '@/lib/auth-context';

function RootNavigator() {
  const { user, ready } = useAuth();

  // Keep the splash visible until the token-check completes.
  // Returning null here means nothing renders while loading —
  // the OS native splash screen stays up (expo-splash-screen hides it later).
  if (!ready) return null;

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Protected guard={user !== null}>
        <Stack.Screen name="(app)" />
      </Stack.Protected>

      <Stack.Protected guard={user === null}>
        <Stack.Screen name="sign-in" />
      </Stack.Protected>
    </Stack>
  );
}

export default function RootLayout() {
  return (
    <AuthProvider>
      <RootNavigator />
    </AuthProvider>
  );
}
