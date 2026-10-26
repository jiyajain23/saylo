import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let client: SupabaseClient | undefined;

export function getSupabase() {
  if (typeof window === "undefined") throw new Error("Authentication is available in the browser.");
  if (!client) {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
    if (!url || !key) throw new Error("Sign-in is not configured. Set the Supabase URL and publishable key.");
    client = createClient(url, key, { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } });
  }
  return client;
}

export async function getAccessToken(minValiditySeconds = 60) {
  const auth = getSupabase().auth;
  let { data: { session }, error } = await auth.getSession();
  if (error) throw new Error("Your session could not be restored. Please sign in again.");
  // Avoid starting a live connection with a token about to expire.
  if (session && (session.expires_at ?? 0) < Date.now() / 1000 + minValiditySeconds) {
    const refreshed = await auth.refreshSession();
    session = refreshed.data.session;
    error = refreshed.error;
  }
  if (error || !session?.access_token) throw new Error("Please sign in to continue.");
  return session.access_token;
}
