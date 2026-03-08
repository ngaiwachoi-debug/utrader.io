import createMiddleware from "next-intl/middleware";
import { withAuth } from "next-auth/middleware";
import { NextRequest, NextResponse } from "next/server";
import { routing } from "./i18n/routing";

const publicPages = ["/", "/login", "/dashboard", "/admin-login", "/terms", "/privacy", "/faq", "/how-it-works", "/strategy", "/pricing"];

function detectLocaleFromAcceptLanguage(acceptLanguage: string): string {
  const supported = new Set(routing.locales);
  const parts = acceptLanguage.split(",").map((s) => s.split(";")[0].trim().toLowerCase());
  for (const part of parts) {
    const lang = part.slice(0, 2);
    if (supported.has(lang)) return lang;
    if (lang === "zh" || part.startsWith("zh")) return "zh";
    if (lang === "en" || part.startsWith("en")) return "en";
    if (part.startsWith("tl") || part.startsWith("fil")) return "fil";
  }
  return routing.defaultLocale;
}

const intlMiddleware = createMiddleware(routing);

const authMiddleware = withAuth(
  (req) => intlMiddleware(req),
  {
    callbacks: {
      authorized: ({ token }) => !!token,
    },
    pages: {
      signIn: '/', // Redirect here if not logged in
    },
  }
);

export default function middleware(req: NextRequest) {
  const pathname = req.nextUrl.pathname;
  if (pathname === "/" || pathname === "") {
    const acceptLanguage = req.headers.get("accept-language") || "";
    const locale = detectLocaleFromAcceptLanguage(acceptLanguage);
    return NextResponse.redirect(new URL(`/${locale}`, req.url));
  }
  const publicPathnameRegex = RegExp(
    `^(/(${routing.locales.join("|")}))?(${publicPages.join("|")})?/?$`,
    "i"
  );
  const isPublicPage = publicPathnameRegex.test(pathname);

  if (isPublicPage) {
    return intlMiddleware(req);
  } else {
    return (authMiddleware as any)(req);
  }
}

export const config = {
  // Skip all internal paths (_next, api, etc.)
  matcher: ['/((?!api|_next|.*\\..*).*)']
};