'use client'

import { FolderKanban } from 'lucide-react'

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function ProjectsPage() {
  return (
    <>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold">Proyectos</h1>
          <p className="text-dim text-sm mt-0.5">Sitios y proyectos gestionados</p>
        </div>
      </div>

      <div className="flex flex-col items-center py-24 gap-3 text-center">
        <FolderKanban className="w-10 h-10 text-muted" />
        <p className="text-dim text-sm">No hay proyectos todavía.</p>
        <a href="/dashboard" className="btn-primary text-sm">Ir al Dashboard → Run Audit</a>
      </div>
    </>
  )
}
