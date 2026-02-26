import type { Metadata, Viewport } from 'next'
import { Inter, Geist_Mono } from 'next/font/google'
import { Analytics } from '@vercel/analytics/next'
import { Providers } from '@/components/providers'
import { Toaster } from 'sonner'
import '../globals.css'

const _inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const _geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono" });

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
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${_inter.variable} ${_geistMono.variable} font-sans antialiased`} suppressHydrationWarning>
        <Providers>
          <div suppressHydrationWarning>{children}</div>
        </Providers>
        <Toaster theme="dark" richColors position="top-center" toastOptions={{ style: { background: '#0f172a', border: '1px solid #1e293b', color: '#e2e8f0' } }} />
        <Analytics />
      </body>
    </html>
  )
}
