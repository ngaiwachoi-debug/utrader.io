import type { Metadata, Viewport } from 'next'
import { Analytics } from '@vercel/analytics/next'
import { Providers } from '@/components/providers'
import { Toaster } from 'sonner'
import '../globals.css'

export const metadata: Metadata = {
  title: 'uTrader.io - Crypto Lending Dashboard',
  description: 'Professional automated crypto lending platform. Maximize your lending returns with smart automation.',
  generator: 'v0.app',
  icons: {
    icon: [
      {
        url: '/icon-light-32x32.png',
        media: '(prefers-color-scheme: light)',
      },
      {
        url: '/icon-dark-32x32.png',
        media: '(prefers-color-scheme: dark)',
      },
      {
        url: '/icon.svg',
        type: 'image/svg+xml',
      },
    ],
    apple: '/apple-icon.png',
  },
}

export const viewport: Viewport = {
  themeColor: '#10b981',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  // suppressHydrationWarning: ignores mismatches from browser extensions (e.g. Bitdefender's bis_skin_checked).
  // Pre-hydration: remove extension-injected attributes (e.g. Bitdefender bis_skin_checked) so React doesn't see a server/client mismatch.
  const removeExtensionAttrs = `
    (function(){
      var attrs = ['bis_skin_checked','cz-shortcut-listen','data-gramm','data-new-gr-c-s-check-loaded'];
      function clean(el){
        if (!el || !el.removeAttribute) return;
        attrs.forEach(function(a){ el.removeAttribute(a); });
        if (el.children) for (var i=0;i<el.children.length;i++) clean(el.children[i]);
      }
      function run(){
        clean(document.documentElement);
        if (document.body) clean(document.body);
        if (document.body) {
          var obs = new MutationObserver(function(mutations){
            mutations.forEach(function(m){ if (m.type==='attributes') clean(m.target); });
          });
          obs.observe(document.body, { attributes: true, attributeFilter: attrs, subtree: true });
        }
      }
      function schedule(){ if (document.body) run(); else setTimeout(schedule, 0); }
      if (document.readyState==='loading') { document.addEventListener('DOMContentLoaded', run); schedule(); }
      else run();
    })();
  `;
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: removeExtensionAttrs }} />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet" />
      </head>
      <body className="font-sans antialiased" suppressHydrationWarning>
        <Providers>
          <div suppressHydrationWarning>{children}</div>
        </Providers>
        <Toaster theme="dark" richColors position="top-center" toastOptions={{ style: { background: '#0f172a', border: '1px solid #1e293b', color: '#e2e8f0' } }} />
        <Analytics />
      </body>
    </html>
  )
}
