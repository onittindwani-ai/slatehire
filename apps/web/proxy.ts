import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/** Pages need a session cookie. The API itself checks the session for real, this only saves a round trip to the sign in page. */
export function proxy(request: NextRequest) {
  if (!request.cookies.has("sx_session")) {
    const url = new URL("/login", request.url);
    const here = request.nextUrl.pathname + request.nextUrl.search;
    if (here !== "/") url.searchParams.set("next", here); // so signing in lands on the page that was asked for
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|login|r/|_next/static|_next/image|icon.svg|favicon.ico).*)"],
};
