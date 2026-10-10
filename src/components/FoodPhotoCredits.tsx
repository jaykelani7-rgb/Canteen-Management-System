import { useEffect, useState } from 'react'
import { foodImageSource } from '../lib/foodImageSource'

type Credits = { author: string; source: string; license: string; licenseUrl: string; attribution: string; modifications: string }

/** Attribution travels with the persisted photograph, including future uploads. */
export default function FoodPhotoCredits({ url }: { url?: string }) {
  const [credits, setCredits] = useState<Credits | null>(null)
  const [open, setOpen] = useState(false)
  const safeUrl = foodImageSource(url)
  useEffect(() => {
    setCredits(null)
    if (!safeUrl) return
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 12000)
    fetch(safeUrl, { signal: controller.signal, credentials: 'omit' })
      .then(response => response.ok ? response.json() : null)
      .then(value => {
        if (!controller.signal.aborted && value && typeof value.author === 'string'
            && typeof value.license === 'string' && typeof value.attribution === 'string') setCredits(value)
      }).catch(() => { /* A failed credit request does not prevent browsing food. */ })
      .finally(() => clearTimeout(timer))
    return () => { clearTimeout(timer); controller.abort() }
  }, [safeUrl])
  if (!safeUrl) return null
  return <div className="mt-3 text-xs text-ink-soft">
    <button type="button" className="underline underline-offset-2" aria-expanded={open} onClick={() => setOpen(value => !value)}>Photo credits</button>
    {open && <div className="mt-2 rounded-xl border border-line bg-paper p-3">
      {credits ? <>
        <p>{credits.attribution || credits.author}</p>
        {foodImageSource(credits.source) && <a className="mr-3 underline" href={credits.source} target="_blank" rel="noopener noreferrer">Source</a>}
        {foodImageSource(credits.licenseUrl) ? <a className="underline" href={credits.licenseUrl} target="_blank" rel="noopener noreferrer">{credits.license}</a> : <span>{credits.license}</span>}
        {credits.modifications && <p className="mt-1">{credits.modifications}</p>}
      </> : <a className="underline" href={safeUrl} target="_blank" rel="noopener noreferrer">View photograph attribution</a>}
    </div>}
  </div>
}
