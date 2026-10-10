import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import localFont from 'next/font/local'
import AuthProvider from '@/components/AuthProvider'
import AnalysisSessionProvider from '@/components/AnalysisSessionProvider'
import AppShell from '@/components/shell/AppShell'
import ShellStateProvider from '@/components/shell/ShellStateProvider'
import RouteGuard from '@/components/RouteGuard'
import SiteHeader from '@/components/SiteHeader'
import './globals.css'

// Brandkit v2 §3 webfonts, bundled so builds need no Google Fonts requests.
// Exposed as CSS variables that tailwind fontFamily consumes.
const sora = localFont({
  src: './fonts/Sora-Variable.ttf',
  weight: '100 800',
  style: 'normal',
  variable: '--font-sans',
  display: 'swap',
})

const plexMono = localFont({
  src: [
    { path: './fonts/IBMPlexMono-Regular.ttf', weight: '400', style: 'normal' },
    { path: './fonts/IBMPlexMono-Medium.ttf', weight: '500', style: 'normal' },
  ],
  variable: '--font-mono',
  display: 'swap',
  // Keep Tailwind's monospace fallback stack instead of localFont's Arial.
  adjustFontFallback: false,
})

export const metadata: Metadata = {
  title: 'Yanki — how AI answers talk about your brand',
  description: 'See how AI answers talk about your brand.',
  manifest: '/manifest.webmanifest',
  icons: {
    icon: [
      { url: '/yanki-favicon.svg', type: 'image/svg+xml' },
      { url: '/favicon-32.png', sizes: '32x32', type: 'image/png' },
    ],
    apple: [
      { url: '/apple-touch-180.png', sizes: '180x180', type: 'image/png' },
    ],
  },
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${sora.variable} ${plexMono.variable}`}>
      <body className="min-h-screen bg-surface-muted font-sans text-surface-foreground antialiased">
        {/* Session state is read by the header and the auth screens, so the
            provider wraps everything below it. */}
        <AuthProvider>
          <AnalysisSessionProvider>
            <ShellStateProvider>
              <AppShell>
                <RouteGuard>
                  <SiteHeader />
                  {children}
                </RouteGuard>
              </AppShell>
            </ShellStateProvider>
          </AnalysisSessionProvider>
        </AuthProvider>
      </body>
    </html>
  )
}
