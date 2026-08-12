import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import { Sora, IBM_Plex_Mono } from 'next/font/google'
import AuthProvider from '@/components/AuthProvider'
import AnalysisSessionProvider from '@/components/AnalysisSessionProvider'
import ShellStateProvider from '@/components/shell/ShellStateProvider'
import RouteGuard from '@/components/RouteGuard'
import SiteHeader from '@/components/SiteHeader'
import './globals.css'

// Brandkit v2 §3 webfonts, self-hosted by next/font at build (no runtime CDN,
// no <link> tags). Exposed as CSS variables that tailwind fontFamily consumes.
const sora = Sora({
  subsets: ['latin'],
  weight: ['300', '400', '500', '600'],
  variable: '--font-sans',
  display: 'swap',
})

const plexMono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  variable: '--font-mono',
  display: 'swap',
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
    apple: [{ url: '/apple-touch-180.png', sizes: '180x180', type: 'image/png' }],
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
              <SiteHeader />
              <RouteGuard>{children}</RouteGuard>
            </ShellStateProvider>
          </AnalysisSessionProvider>
        </AuthProvider>
      </body>
    </html>
  )
}
