const KEY = "ragdog.session_id";

export function getSessionId(): string {
  if (typeof window === "undefined") return "ssr";
  let id = window.localStorage.getItem(KEY);
  if (!id) {
    id = crypto.randomUUID();
    window.localStorage.setItem(KEY, id);
  }
  return id;
}

export function resetSession(): string {
  if (typeof window === "undefined") return "ssr";
  const id = crypto.randomUUID();
  window.localStorage.setItem(KEY, id);
  return id;
}
