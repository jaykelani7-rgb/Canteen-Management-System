import { useState } from 'react'
import { foodImageSource } from '../lib/foodImageSource'

/** Keeps the existing image area useful even when a menu photograph is absent or fails. */
export default function FoodImage({ src, alt, className = '' }: {
  src?: string | null; alt: string; className?: string
}) {
  const source = foodImageSource(src)
  return <FoodImageAttempt key={source ?? 'missing'} source={source} alt={alt} className={className} />
}

function FoodImageAttempt({ source, alt, className }: { source: string | null; alt: string; className: string }) {
  const [failed, setFailed] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const canLoad = Boolean(source && !failed)
  return <span role="img" aria-label={loaded ? alt : `${alt} — photo unavailable`} className={`relative block h-full w-full overflow-hidden bg-paper ${className}`}>
    <span aria-hidden="true" className="absolute inset-0 grid place-items-center text-[#C37A50]">
      <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="h-1/2 w-1/2 max-h-16 max-w-16">
        <circle cx="25" cy="24" r="12" /><circle cx="25" cy="24" r="8" />
        <path d="M6 8v9a4 4 0 0 0 8 0V8M10 8v32M40 8v32M40 8c-5 4-5 12 0 15" />
      </svg>
    </span>
    {canLoad && <img key={source} src={source!} alt="" aria-hidden="true" loading="lazy" decoding="async"
      className={`absolute inset-0 h-full w-full object-cover ${loaded ? 'opacity-100' : 'opacity-0'}`}
      onLoad={() => setLoaded(true)} onError={() => { setLoaded(false); setFailed(true) }} />}
  </span>
}
