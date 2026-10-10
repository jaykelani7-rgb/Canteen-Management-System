import { useEffect, useRef, useState } from 'react'
import { adminOperationsApi, type FoodImageAsset } from '../lib/adminOperationsApi'

const inputClass = 'mt-1 w-full rounded-xl border border-[#E5DFD7] bg-white p-2.5 text-xs font-normal text-[#1D1A16] outline-none focus:border-[#F25C2C]'
const buttonClass = 'rounded-xl border border-[#E5DFD7] bg-white px-3 py-2 text-xs font-bold text-stone-700 disabled:opacity-50'
export const FOOD_IMAGE_MAX_BYTES = 5 * 1024 * 1024
export function validateFoodImageFile(file: File): string {
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) return 'Choose a JPEG, PNG or WebP photograph.'
  if (!file.size || file.size > FOOD_IMAGE_MAX_BYTES) return 'The photograph must be nonempty and no larger than 5 MiB.'
  return ''
}

function ProtectedPreview({ id, onReady }: { id: string; onReady: (ready: boolean) => void }) {
  const [url, setUrl] = useState(''), [error, setError] = useState(''), [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController(); let active = true, objectUrl = ''
    setUrl(''); setError(''); onReady(false)
    adminOperationsApi.foodImageBlob(id, controller.signal).then(blob => {
      if (!active) return
      objectUrl = URL.createObjectURL(blob); setUrl(objectUrl)
    }).catch(cause => { if (active) setError((cause as Error).message) })
    return () => { active = false; controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [id, retry, onReady])
  return <div className="space-y-2">
    <div className="relative flex h-40 items-center justify-center overflow-hidden rounded-2xl bg-stone-100 text-xs text-stone-500">
      {!url && !error && <span role="status">Loading photograph…</span>}
      {url && !error && <img key={url} src={url} alt="Selected food photograph" className="h-full w-full object-contain opacity-0" onLoad={event => { event.currentTarget.classList.remove('opacity-0'); onReady(true) }} onError={() => { setError('This photograph could not be displayed. Retry the preview.'); onReady(false) }} />}
      {error && <span role="alert" className="p-4 text-center text-red-700">{error}</span>}
    </div>
    {error && <button type="button" onClick={() => setRetry(value => value + 1)} className={buttonClass}>Retry preview</button>}
  </div>
}

interface Props {
  dishName: string; imageId: string | null; confirmed: boolean; disabled: boolean;
  onImageChange: (id: string | null) => void; onConfirmedChange: (value: boolean) => void;
  onBusyChange: (value: boolean) => void; onPendingChange: (value: boolean) => void;
}

export default function AdminFoodImagePicker({ dishName, imageId, confirmed, disabled, onImageChange, onConfirmedChange, onBusyChange, onPendingChange }: Props) {
  const [mode, setMode] = useState<'upload' | 'library'>('upload')
  const [file, setFile] = useState<File | null>(null), [localUrl, setLocalUrl] = useState(''), [fileReady, setFileReady] = useState(false)
  const [source, setSource] = useState(''), [license, setLicense] = useState(''), [attribution, setAttribution] = useState('')
  const [author, setAuthor] = useState(''), [licenseUrl, setLicenseUrl] = useState(''), [modifications, setModifications] = useState('')
  const [rights, setRights] = useState(false), [uploading, setUploading] = useState(false), [error, setError] = useState('')
  const [selected, setSelected] = useState<FoodImageAsset | null>(null), [previewReady, setPreviewReady] = useState(false)
  const [query, setQuery] = useState(''), [library, setLibrary] = useState<FoodImageAsset[]>([]), [loading, setLoading] = useState(false), [reload, setReload] = useState(0)
  const uploadLock = useRef(false), mounted = useRef(true), fileInput = useRef<HTMLInputElement>(null)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  useEffect(() => { onPendingChange(Boolean(file)) }, [file, onPendingChange])
  useEffect(() => { onBusyChange(uploading) }, [uploading, onBusyChange])
  useEffect(() => {
    setLocalUrl(''); setFileReady(false)
    if (!file) return
    const url = URL.createObjectURL(file); setLocalUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [file])
  useEffect(() => {
    let active = true; setSelected(null); setPreviewReady(false)
    if (imageId) adminOperationsApi.foodImage(imageId).then(asset => { if (active) setSelected(asset) }).catch(cause => { if (active) setError((cause as Error).message) })
    return () => { active = false }
  }, [imageId])
  useEffect(() => {
    if (mode !== 'library') return
    let active = true; setLoading(true); setError('')
    const timeout = setTimeout(() => {
      adminOperationsApi.foodImages(query).then(assets => { if (active) setLibrary(assets) })
        .catch(cause => { if (active) setError((cause as Error).message) }).finally(() => { if (active) setLoading(false) })
    }, 200)
    return () => { active = false; clearTimeout(timeout) }
  }, [mode, query, reload])
  const discardFile = () => { setFile(null); setRights(false); if (fileInput.current) fileInput.current.value = '' }
  const choose = (asset: FoodImageAsset) => { discardFile(); setError(''); setSelected(asset); onImageChange(asset.id); onConfirmedChange(false) }
  const upload = async () => {
    if (uploadLock.current || !file || disabled) return
    if (!dishName.trim()) { setError('Enter the dish name before uploading.'); return }
    if (!source.trim() || !license.trim() || !attribution.trim() || !rights || !fileReady) { setError('Provide the source, license and credit, confirm image rights, and wait for a valid preview.'); return }
    if (licenseUrl.trim()) {
      try { const url = new URL(licenseUrl); if (url.protocol !== 'https:' || url.username || url.password) throw new Error() }
      catch { setError('The license link must be a public HTTPS URL.'); return }
    }
    uploadLock.current = true; setUploading(true); setError('')
    try {
      const asset = await adminOperationsApi.uploadFoodImage({ file, dishName: dishName.trim(), source: source.trim(), license: license.trim(), attribution: attribution.trim(), author: author.trim(), licenseUrl: licenseUrl.trim(), modifications: modifications.trim(), rightsConfirmed: rights })
      if (mounted.current) { choose(asset); setReload(value => value + 1) }
    } catch (cause) { if (mounted.current) setError((cause as Error).message) }
    finally { uploadLock.current = false; if (mounted.current) setUploading(false) }
  }
  return <section className="space-y-3 rounded-2xl border border-[#E5DFD7] bg-[#FAF7F3] p-4" aria-label="Food photograph">
    <div><h5 className="text-xs font-bold uppercase tracking-wider text-stone-700">Food Photograph</h5><p className="mt-1 text-[11px] text-stone-500">Upload once or reuse your library. A suitable photograph is required before a dish is available to students.</p></div>
    {imageId && !file && <div className="space-y-2">
      <ProtectedPreview key={imageId} id={imageId} onReady={setPreviewReady} />
      {selected && <div className="text-[11px] text-stone-600"><p className="font-bold">{selected.dishName}</p><p className="break-words">Source: {selected.source}</p><p>License: {selected.license}</p><p className="break-words">Credit: {selected.attribution}</p>{selected.author && <p>Author: {selected.author}</p>}{selected.modifications && <p>Modifications: {selected.modifications}</p>}</div>}
      <label className="flex items-start gap-2 text-xs text-stone-700"><input type="checkbox" checked={confirmed} disabled={disabled || !previewReady} onChange={event => onConfirmedChange(event.target.checked)} className="mt-0.5 accent-[#F25C2C]" /><span>I confirm this photograph shows the actual type of dish being sold.</span></label>
      <button type="button" disabled={disabled} onClick={() => { onImageChange(null); onConfirmedChange(false); setError('') }} className={buttonClass}>Remove photograph</button>
    </div>}
    <div className="flex gap-2">{(['upload', 'library'] as const).map(value => <button key={value} type="button" disabled={disabled || uploading} onClick={() => { discardFile(); setError(''); setMode(value) }} className={`${buttonClass} ${mode === value ? 'border-[#F25C2C] text-[#F25C2C]' : ''}`}>{value === 'upload' ? 'Upload photograph' : 'Image library'}</button>)}</div>
    {mode === 'upload' ? <div className="space-y-3">
      <label className="block text-xs font-bold text-stone-700">Choose from device<input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" disabled={disabled || uploading} className={inputClass} onChange={event => { const picked = event.target.files?.[0]; if (!picked) return; const problem = validateFoodImageFile(picked); setError(problem); if (problem) { discardFile(); return } setFile(picked); setRights(false) }} /></label>
      <p className="text-[11px] text-stone-500">JPEG, PNG or WebP · up to 5 MiB / 8 megapixels. Optimized and stored securely on the server.</p>
      {file && <>
        <div className="h-40 overflow-hidden rounded-2xl bg-stone-100">{localUrl && <img key={localUrl} src={localUrl} alt="New upload preview" className="h-full w-full object-contain opacity-0" onLoad={event => { const image = event.currentTarget; if (image.naturalWidth * image.naturalHeight > 8_000_000) { setError('Choose a photograph with no more than 8 megapixels.'); setFileReady(false); return } image.classList.remove('opacity-0'); setFileReady(true) }} onError={() => { setError('The selected file is not a readable photograph.'); setFileReady(false) }} />}</div>
        <label className="block text-xs font-bold text-stone-700">Source / original URL<input maxLength={1000} disabled={uploading} value={source} onChange={event => setSource(event.target.value)} placeholder="My own photograph, or original source URL" className={inputClass} /></label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3"><label className="text-xs font-bold text-stone-700">License / permission<input maxLength={255} disabled={uploading} value={license} onChange={event => setLicense(event.target.value)} placeholder="Owned photograph, CC BY 4.0…" className={inputClass} /></label><label className="text-xs font-bold text-stone-700">Author (optional)<input maxLength={255} disabled={uploading} value={author} onChange={event => setAuthor(event.target.value)} className={inputClass} /></label></div>
        <label className="block text-xs font-bold text-stone-700">Attribution / credit<input maxLength={1000} disabled={uploading} value={attribution} onChange={event => setAttribution(event.target.value)} placeholder="Photograph by… / own canteen photograph" className={inputClass} /></label>
        <label className="block text-xs font-bold text-stone-700">License link (optional)<input maxLength={1000} disabled={uploading} value={licenseUrl} onChange={event => setLicenseUrl(event.target.value)} inputMode="url" placeholder="https://…" className={inputClass} /></label>
        <label className="block text-xs font-bold text-stone-700">Modifications (optional)<input maxLength={1000} disabled={uploading} value={modifications} onChange={event => setModifications(event.target.value)} placeholder="Cropped, resized…" className={inputClass} /></label>
        <label className="flex items-start gap-2 text-xs text-stone-700"><input type="checkbox" checked={rights} disabled={uploading} onChange={event => setRights(event.target.checked)} className="mt-0.5 accent-[#F25C2C]" /><span>I own this photograph or have permission under the stated license to use it commercially.</span></label>
        <div className="flex flex-wrap gap-2"><button type="button" disabled={disabled || uploading || !fileReady || !rights} onClick={() => void upload()} className="rounded-xl bg-[#F25C2C] px-4 py-2 text-xs font-bold text-white disabled:opacity-50">{uploading ? 'Uploading…' : 'Upload to library'}</button><button type="button" disabled={uploading} onClick={discardFile} className={buttonClass}>Discard selection</button></div>
        <p className="text-[11px] text-stone-500">Upload before saving the dish; uploading alone does not publish it.</p>
      </>}
    </div> : <div className="space-y-2">
      <label className="block text-xs font-bold text-stone-700">Search image library<input disabled={disabled} value={query} onChange={event => setQuery(event.target.value)} placeholder="Dish name, source or credit…" className={inputClass} /></label>
      {loading ? <p role="status" className="text-xs text-stone-500">Loading library…</p> : <div className="max-h-48 space-y-2 overflow-y-auto">
        {!library.length && <p className="text-xs text-stone-500">No photographs found. Upload your first photograph.</p>}
        {library.map(asset => <div key={asset.id} className="flex items-center justify-between gap-3 rounded-xl border border-[#E5DFD7] bg-white p-3"><div className="min-w-0 text-xs"><p className="font-bold">{asset.dishName}</p><p className="break-words text-[11px] text-stone-500">{asset.license} · {asset.attribution}</p></div><button type="button" disabled={disabled} onClick={() => choose(asset)} className={buttonClass}>{imageId === asset.id ? 'Selected' : 'Preview / select'}</button></div>)}
      </div>}
      <button type="button" disabled={disabled || loading} onClick={() => setReload(value => value + 1)} className={buttonClass}>Refresh library</button>
    </div>}
    {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-xs text-red-700">{error}</p>}
  </section>
}
