import type { Metadata } from 'next'
import { Inter, DM_Mono } from 'next/font/google'
import './globals.css'

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
})
const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  variable: '--font-dm-mono',
  display: 'swap',
})

export const metadata: Metadata = {
  title: { default: 'WPRecover 2.0', template: '%s | WPRecover' },
  description: 'WordPress & WooCommerce Recovery Platform — AI-powered site recovery',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={`${inter.variable} ${dmMono.variable}`} suppressHydrationWarning>
      <body className="bg-bg text-[#e2e8f0] font-sans antialiased">
        {children}
      </body>
    </html>
  )
}
