"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import type { Session } from "@supabase/supabase-js";
import { getSupabase } from "@/lib/auth";

type AuthState = { session: Session | null; loading: boolean; error: string | null };
const AuthContext = createContext<AuthState>({ session: null, loading: true, error: null });
export function useAuth() { return useContext(AuthContext); }

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({ session: null, loading: true, error: null });
  useEffect(() => {
    let alive = true;
    let unsubscribe = () => {};
    try {
      const auth = getSupabase().auth;
      const { data: { subscription } } = auth.onAuthStateChange((_event, session) => {
        if (alive) setState({ session, loading: false, error: null });
      });
      unsubscribe = () => subscription.unsubscribe();
      void auth.getSession().then(({ data, error }) => {
        if (alive) setState({ session: data.session, loading: false, error: error ? "Please sign in again." : null });
      }).catch(() => { if (alive) setState({ session: null, loading: false, error: "Sign-in is unavailable. Please retry." }); });
    } catch (error) {
      setState({ session: null, loading: false, error: error instanceof Error ? error.message : "Sign-in is unavailable." });
    }
    return () => { alive = false; unsubscribe(); };
  }, []);
  return <AuthContext.Provider value={state}>{children}</AuthContext.Provider>;
}

export function AuthBoundary({ children }: { children: React.ReactNode }) {
  const { session, loading } = useContext(AuthContext);
  const pathname = usePathname();
  if (pathname === "/") return <>{children}</>;
  if (loading) return <div className="state-message" role="status">Restoring your session…</div>;
  if (!session) return <LoginForm />;
  // Changing users unmounts media, requests, and previously rendered private data.
  return <div key={session.user.id}>{children}</div>;
}

export function AuthControls() {
  const { session, loading } = useContext(AuthContext);
  const [error, setError] = useState("");
  async function logout() {
    const { error } = await getSupabase().auth.signOut({ scope: "local" });
    if (error) setError("Could not sign out. Please retry.");
  }
  if (loading) return null;
  return <div style={{ display: "flex", alignItems: "center", gap: ".5rem" }}>
    {session ? <button className="btn btn-ghost" onClick={() => void logout()}>Sign out</button>
      : <a className="btn btn-ghost" href="/login">Sign in</a>}
    {error && <span role="alert">{error}</span>}
  </div>;
}

export function LoginForm() {
  const state = useContext(AuthContext);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [signup, setSignup] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function github() {
    setBusy(true); setMessage("");
    try {
      const { error } = await getSupabase().auth.signInWithOAuth({
        provider: "github", options: { redirectTo: `${window.location.origin}/login` }
      });
      if (error) throw error;
    } catch { setMessage("GitHub sign-in is unavailable. Please retry later."); }
    finally { setBusy(false); }
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true); setMessage("");
    try {
      const auth = getSupabase().auth;
      const result = signup
        ? await auth.signUp({ email, password, options: { emailRedirectTo: `${window.location.origin}/login` } })
        : await auth.signInWithPassword({ email, password });
      if (result.error) throw result.error;
      setPassword("");
      if (signup && !result.data.session) setMessage("Check your email to confirm your account, then sign in.");
    } catch {
      setMessage(signup ? "Could not create the account. Check the details or try again later." : "Sign-in failed. Check your email, password, and email confirmation.");
    } finally { setBusy(false); }
  }
  return <section className="card" style={{ maxWidth: 420, margin: "2rem auto", padding: "2rem" }}>
    <h1>{signup ? "Create your Saylo account" : "Sign in to Saylo"}</h1>
    <p style={{ margin: "1rem 0" }}>Your practice sessions and analysis are private to your account.</p>
    <p style={{ marginBottom: "1rem", fontSize: ".8125rem" }}>Live audio, camera frames, and session context are sent to Google Gemini. Transcripts and analysis are stored in Supabase. Use sample interview data for this student demo.</p>
    {state.error && <p role="alert">{state.error}</p>}
    {process.env.NEXT_PUBLIC_SUPABASE_GITHUB_ENABLED === "true" &&
      <button className="btn btn-primary" style={{ marginBottom: "1rem" }} disabled={busy || !!state.error} onClick={() => void github()}>Continue with GitHub</button>}
    <form onSubmit={(event) => void submit(event)} style={{ display: "grid", gap: "1rem" }}>
      <label>Email<input className="input" type="email" autoComplete="email" required value={email} onChange={event => setEmail(event.target.value)} /></label>
      <label>Password<input className="input" type="password" autoComplete={signup ? "new-password" : "current-password"} required minLength={8} value={password} onChange={event => setPassword(event.target.value)} /></label>
      <button className="btn btn-primary" disabled={busy || !!state.error}>{busy ? "Please wait…" : signup ? "Create account" : "Sign in"}</button>
    </form>
    {message && <p role="status" style={{ marginTop: "1rem" }}>{message}</p>}
    <button className="btn btn-ghost" disabled={busy} onClick={() => { setSignup(!signup); setMessage(""); }}>{signup ? "Already have an account? Sign in" : "Create an account"}</button>
  </section>;
}
