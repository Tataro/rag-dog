import { createContext, use, useEffect, useState, type PropsWithChildren } from 'react';
import { GoogleSignin } from '@react-native-google-signin/google-signin';

import { api, UnauthorizedError } from './api';
import { clearToken, loadToken, saveToken } from './auth-storage';
import { config } from './config';
import type { User } from './types';

type AuthContextValue = {
  user: User | null;
  /** true once the initial token-check has completed */
  ready: boolean;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
};

// Configure the native Google sign-in once at module load (the official guidance
// is to call configure() a single time, not on every signIn()).
GoogleSignin.configure({
  webClientId: config.googleWebClientId,
  iosClientId: config.googleIosClientId,
});

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = use(AuthContext);
  if (!value) {
    throw new Error('useAuth must be called inside <AuthProvider>');
  }
  return value;
}

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  // On mount: restore session from secure storage
  useEffect(() => {
    let cancelled = false;

    async function restore() {
      try {
        const token = await loadToken();
        if (!token) return;
        const me = await api.me();
        if (!cancelled) setUser(me);
      } catch (err) {
        if (err instanceof UnauthorizedError) {
          await clearToken().catch(() => {});
        }
        // Any other error (network, etc.) — stay signed out, non-fatal
      } finally {
        if (!cancelled) setReady(true);
      }
    }

    restore();
    return () => {
      cancelled = true;
    };
  }, []);

  async function signIn(): Promise<void> {
    await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });

    // v16 signIn() returns SignInResponse = SignInSuccessResponse | CancelledResponse
    // SignInSuccessResponse = { type: 'success'; data: User }
    // CancelledResponse     = { type: 'cancelled'; data: null }
    // User.idToken is string | null
    const result = await GoogleSignin.signIn();

    if (result.type === 'cancelled') {
      // User dismissed the dialog — not an error, just return
      return;
    }

    // result.type === 'success'
    const idToken = result.data.idToken;
    if (!idToken) {
      throw new Error(
        'Google sign-in succeeded but returned no idToken. ' +
          'Ensure a webClientId is configured and the project has an OAuth 2.0 Web client.'
      );
    }

    const { session_token, user: me } = await api.googleLogin(idToken);
    await saveToken(session_token);
    setUser(me);
  }

  async function signOut(): Promise<void> {
    // Both clears are best-effort: a SecureStore/native failure must not leave the
    // user stuck in the authenticated UI — always fall through to setUser(null).
    await clearToken().catch(() => {});
    await GoogleSignin.signOut().catch(() => {});
    setUser(null);
  }

  return (
    <AuthContext value={{ user, ready, signIn, signOut }}>
      {children}
    </AuthContext>
  );
}
