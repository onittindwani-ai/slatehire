import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
const HOP = new Set(["connection", "keep-alive", "transfer-encoding", "content-encoding", "content-length"]);

/** Forward /api/* to the private API. Adds the session from the cookie. Mutations need the x-slatehire header, which a cross site page cannot send. */
async function forward(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const joined = path.join("/");
  if (joined.startsWith("auth/login") || joined.startsWith("webhooks") || joined.startsWith("tools")) return NextResponse.json({ error: { message: "Not found." } }, { status: 404 });
  if (!["GET", "HEAD"].includes(request.method) && request.headers.get("x-slatehire") !== "1") {
    return NextResponse.json({ error: { message: "Missing request header." } }, { status: 400 });
  }
  const token = (await cookies()).get("sx_session")?.value;
  const url = new URL(request.url);
  // One connection per request: the API closes the connection after it answers an unexpected error, and a pooled socket reused right after
  // it made the next request fail with a 502.
  const headers: Record<string, string> = { accept: request.headers.get("accept") ?? "*/*", connection: "close" };
  const ct = request.headers.get("content-type");
  if (ct) headers["content-type"] = ct;
  const fn = request.headers.get("x-filename");
  if (fn) headers["x-filename"] = fn.slice(0, 200);
  if (token) headers["x-session"] = token;
  const ip = request.headers.get("x-forwarded-for");
  if (ip) headers["x-forwarded-for"] = ip;
  const body = ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer();
  const send = () => fetch(`${API}/api/${joined}${url.search}`, {
    method: request.method, headers, body, signal: request.signal, cache: "no-store",
  });
  let upstream: Response;
  try {
    try {
      upstream = await send();
    } catch (first) {
      if (request.signal.aborted || !["GET", "HEAD"].includes(request.method)) throw first;
      upstream = await send(); // a reading request is safe to repeat once if the connection was closed under it
    }
  } catch {
    return NextResponse.json({ error: { message: "The server is not reachable. Check that the API is running." } }, { status: 502 });
  }
  const out = new Headers();
  upstream.headers.forEach((v, k) => { if (!HOP.has(k.toLowerCase())) out.set(k, v); });
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export { forward as GET, forward as POST, forward as PUT, forward as PATCH, forward as DELETE };
export const dynamic = "force-dynamic";
