import Link from "next/link";

export default function NotFound() {
  return (
    <main className="cf-login" id="main">
      <div className="cf-login__card" style={{ display: "grid", gap: 21 }}>
        <div>
          <h1 className="cf-title">That page does not exist</h1>
          <p className="cf-sub">The address may be old or mistyped. Nothing was changed.</p>
        </div>
        <Link href="/" className="sx-btn sx-btn--primary" style={{ justifySelf: "start" }}>Back to the pipeline</Link>
      </div>
    </main>
  );
}
