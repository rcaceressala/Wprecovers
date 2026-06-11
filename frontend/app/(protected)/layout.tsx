import { Sidebar } from '@/components/Sidebar'
import { AuthGuard } from '@/components/AuthGuard'

export default function ProtectedLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto min-w-0">
          <div className="px-6 py-8 md:px-8 max-w-[1400px] mx-auto">
            {children}
          </div>
        </main>
      </div>
    </AuthGuard>
  )
}
