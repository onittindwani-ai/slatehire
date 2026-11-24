import { NextResponse } from "next/server";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/** Sign in: ask the API for a token and keep it in an httpOnly cookie. The token never reaches page JavaScript. */
export async function POST(request: Request) {
  if (request.headers.get("x-slatehire") !== "1") return NextResponse.json({ error: { message: "Bad request." } }, { status: 400 });
  const body = await request.text();
  let upstream: Response;
  try {
    upstream = await fetch(`${API}/api/auth/login`, { method: "POST", headers: { "content-type": "application/json", "x-forwarded-for": request.headers.get("x-forwarded-for") ?? "" }, body });
  } catch {
    return NextResponse.json({ error: { message: "The server is not reachable. Check that the API is running." } }, { status: 502 });
  }
  const data = await upstream.json().catch(() => ({}));
  if (!upstream.ok) return NextResponse.json({ error: { message: data?.error?.message ?? "Sign in failed." } }, { status: upstream.status });
  const res = NextResponse.json({ user: data.user, role: data.role });
  res.cookies.set("sx_session", data.token, { httpOnly: true, sameSite: "lax", secure: process.env.NODE_ENV === "production" && process.env.INSECURE_COOKIES !== "1", path: "/", maxAge: 8 * 3600 });
  return res;
}

export async function DELETE(request: Request) {
  if (request.headers.get("x-slatehire") !== "1") return NextResponse.json({ error: { message: "Bad request." } }, { status: 400 });
  const res = NextResponse.json({ ok: true });
  res.cookies.delete("sx_session");
  return res;
}
