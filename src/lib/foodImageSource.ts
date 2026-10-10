/** Public food photographs may use bundled local assets or an HTTPS image URL. */
export function foodImageSource(value?: string | null): string | null {
  const source = value?.trim() || ''
  if (!source || /[\\\u0000-\u001f]/.test(source)) return null
  if (source.startsWith('/')) return source.startsWith('//') ? null : source
  try {
    const url = new URL(source)
    return url.protocol === 'https:' && !url.username && !url.password ? url.href : null
  } catch { return null }
}
