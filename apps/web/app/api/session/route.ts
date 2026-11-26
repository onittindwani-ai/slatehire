import { cookies } from "next/headers";
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
  // A browser that signed in before carries a signed note (never a session). The API counts its tries on their own, so one stranger's bad tries behind a shared address cannot keep the owner out.
  const device = (await cookies()).get("sx_device")?.value;
  const headers: Record<string, string> = { "content-type": "application/json", "x-forwarded-for": lastHop(request.headers.get("x-forwarded-for")) };
  if (device) headers["x-device"] = device;
  let upstream: Response;
  try {
    upstream = await fetch(`${API}/api/auth/login`, { method: "POST", headers, body });
  } catch {
    return NextResponse.json({ error: { message: "The server is not reachable. Check that the API is running." } }, { status: 502 });
  }
  const data = await upstream.json().catch(() => ({}));
  if (!upstream.ok) return NextResponse.json({ error: { message: data?.error?.message ?? "Sign in failed." } }, { status: upstream.status });
  const res = NextResponse.json({ user: data.user, role: data.role });
  const secure = process.env.NODE_ENV === "production" && process.env.INSECURE_COOKIES !== "1";
  res.cookies.set("sx_session", data.token, { httpOnly: true, sameSite: "lax", secure, path: "/", maxAge: 8 * 3600 });
  if (typeof data.device === "string") res.cookies.set("sx_device", data.device, { httpOnly: true, sameSite: "lax", secure, path: "/", maxAge: 7 * 24 * 3600 }); // kept after sign out on purpose: it only says "this browser signed in before"
  return res;
}

export async function DELETE(request: Request) {
  if (request.headers.get("x-slatehire") !== "1") return NextResponse.json({ error: { message: "Bad request." } }, { status: 400 });
  const res = NextResponse.json({ ok: true });
  res.cookies.delete("sx_session");
  return res;
}
