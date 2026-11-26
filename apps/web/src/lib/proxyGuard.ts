/** Rules for what the web proxy will forward to the private API. Kept apart from the route so they can be tested without a server. */

const BLOCKED_FIRST = new Set(["webhooks", "tools"]); // the signed webhooks go to the API directly, not through the web app
const MAX_BODY_LOGIN = 8 * 1024; // a sign in is a few hundred bytes
const MAX_BODY_API = 25 * 1024 * 1024; // the largest legitimate request is a resume file (5 MB by default); this matches the API's own MAX_BODY_BYTES default

/** The path segments to forward, or null when the request must be refused. A segment that is "." or "..", or holds a slash, a backslash or a percent sign
 *  (so it could be decoded into one later), is refused; so is auth/login (signing in goes through /api/session so the token stays out of page scripts),
 *  and anything under webhooks or tools. Matched by whole segment, never by a text prefix. */
export function safePath(segments: string[]): string | null {
  if (!segments.length) return null;
  for (const seg of segments) {
    if (!seg || seg === "." || seg === ".." || /[\\/%\u0000-\u001f]/.test(seg)) return null;
  }
  const [first, second] = segments.map((x) => x.toLowerCase());
  if (BLOCKED_FIRST.has(first!) || (first === "auth" && second === "login")) return null;
  return segments.join("/");
}

/** True when the declared body length is acceptable. A body with no declared length is counted while it is read (see readLimited). */
export function bodyAllowed(contentLength: string | null, limit: number): boolean {
  if (contentLength === null || contentLength === "") return true;
  return /^\d+$/.test(contentLength) && Number(contentLength) <= limit;
}

/** Read a request body but stop as soon as it is larger than `limit` bytes. Returns null when it was too large. */
export async function readLimited(request: Request, limit: number): Promise<ArrayBuffer | null> {
  if (!bodyAllowed(request.headers.get("content-length"), limit)) return null;
  if (!request.body) return new ArrayBuffer(0);
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > limit) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  const out = new Uint8Array(total);
  let at = 0;
  for (const c of chunks) {
    out.set(c, at);
    at += c.byteLength;
  }
  return out.buffer;
}

export { MAX_BODY_API, MAX_BODY_LOGIN };
