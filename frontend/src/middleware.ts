import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const sessionId = request.cookies.get("session_id");

  // If trying to access interview without a session_id, redirect to home
  if (!sessionId && request.nextUrl.pathname.startsWith("/interview")) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: "/interview/:path*",
};
