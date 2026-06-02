"use client";

import { useEffect, useRef } from "react";
import { useAuth } from "@/lib/auth-context";

interface GoogleAccountsId {
  initialize: (config: { client_id: string; callback: (resp: { credential: string }) => void }) => void;
  renderButton: (parent: HTMLElement, options: { theme: string; size: string }) => void;
}

declare global {
  interface Window {
    google?: {
      accounts: { id: GoogleAccountsId };
    };
  }
}

export function GoogleSignInButton() {
  const { loginWithGoogle } = useAuth();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
    if (!clientId) { console.error("NEXT_PUBLIC_GOOGLE_CLIENT_ID is not set"); return; }
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = () => {
      window.google?.accounts.id.initialize({
        client_id: clientId,
        callback: (resp: { credential: string }) => {
          loginWithGoogle(resp.credential).catch((e) => alert(`Sign-in failed: ${e.message}`));
        },
      });
      if (ref.current) window.google?.accounts.id.renderButton(ref.current, { theme: "outline", size: "large" });
    };
    document.body.appendChild(script);
    return () => {
      script.onload = null; // prevent a stale load callback from rendering a duplicate button
      script.remove();
    };
  }, [loginWithGoogle]);

  return <div ref={ref} />;
}
