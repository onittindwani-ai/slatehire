"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button, Card, Field } from "@sendora/ui-kit";
import { api } from "@/lib/api";

/** The page the person asked for before being sent here, only when it is a path on this site. */
function afterSignIn(): string {
  try {
    const next = new URLSearchParams(window.location.search).get("next") ?? "";
    // Resolve it against this site: a value that lands on another origin (for example a slash, a tab, then a host name) is dropped.
    const url = new URL(next, window.location.origin);
    return next.startsWith("/") && url.origin === window.location.origin ? url.pathname + url.search + url.hash : "/";
  } catch {
    return "/";
  }
}

export default function Login() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const demoHint = process.env.NEXT_PUBLIC_DEMO_HINT === "1";

  async function submit() {
    setError(null);
    try {
      await api("/session", { method: "POST", json: { email, password } });
    } catch (e) {
      setError((e as Error).message);
      throw e;
    }
    router.replace(afterSignIn());
    router.refresh();
  }

  return (
    <main className="cf-login" id="main">
      <Card className="cf-login__card">
        <div>
          <h1 className="cf-title">Slatehire</h1>
          <p className="cf-sub">Sign in to your hiring desk.</p>
        </div>
        <form onSubmit={(e) => { e.preventDefault(); }} style={{ display: "grid", gap: 21 }}>
          <Field label="Email" type="email" autoComplete="username" value={email} onChange={setEmail} validate={(v) => (/^\S+@\S+\.\S+$/.test(v) ? null : "Add an @ and a domain, like name@company.com")} />
          <Field label="Password" type="password" autoComplete="current-password" value={password} onChange={setPassword} />
          {error ? <p role="alert" className="sx-field__error" style={{ margin: 0 }}>{error}</p> : null}
          <Button type="submit" variant="primary" disabled={!email || !password} disabledReason="Enter your email and password" onClick={submit}>Sign in</Button>
        </form>
        {demoHint ? <p className="cf-mini" style={{ margin: 0 }}>Demo sign in: owner@example.test with the password demo-password-1. Demo data only.</p> : null}
      </Card>
    </main>
  );
}
