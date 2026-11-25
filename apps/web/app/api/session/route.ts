import { NextResponse } from "next/server";
import { lastHop } from "@/lib/clientIp";
import { MAX_BODY_LOGIN, readLimited } from "@/lib/proxyGuard";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/** Sign in: ask the API for a token and keep it in an httpOnly cookie. The token never reaches page JavaScript. */
export async function POST(request: Request) {
  if (request.headers.get("x-slatehire") !== "1") return NextResponse.json({ error: { message: "Bad request." } }, { status: 400 });
  const raw = await readLimited(request, MAX_BODY_LOGIN); // a sign in is a few hundred bytes; a larger body is refused before it is held in memory
  if (raw === null) return NextResponse.json({ error: { message: "The request is too large." } }, { status: 413 });
  const body = new TextDecoder().decode(raw);
  let upstream: Response;
  try {
    upstream = await fetch(`${API}/api/auth/login`, { method: "POST", headers: { "content-type": "application/json", "x-forwarded-for": lastHop(request.headers.get("x-forwarded-for")) }, body });
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
