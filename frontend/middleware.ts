import createMiddleware from 'next-intl/middleware';
import { withAuth } from "next-auth/middleware";
import { NextRequest } from "next/request";

const locales = ['en', 'zh', 'ko', 'ru', 'de'];
const publicPages = ['/', '/login', '/dashboard', '/admin-login']; // Dashboard public for "Dev: Login as"; admin-login for admin Google sign-in

const intlMiddleware = createMiddleware({
  locales,
  defaultLocale: 'en'
});

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
  const publicPathnameRegex = RegExp(
    `^(/(${locales.join('|')}))?(${publicPages.join('|')})?/?$`,
    'i'
  );
  const isPublicPage = publicPathnameRegex.test(req.nextUrl.pathname);

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