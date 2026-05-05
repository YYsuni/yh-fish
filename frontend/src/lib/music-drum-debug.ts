export type MusicDrumItem = {
	key: string
	label: string
	x: number
	y: number
	w: number
	h: number
	similarity: number | null
}

export type MusicDrumDebug = {
	items: MusicDrumItem[]
}

export function parseMusicDrumDebug(raw: unknown): MusicDrumDebug | null {
	if (raw == null || typeof raw !== 'object') return null
	const o = raw as Record<string, unknown>
	const arr = o.items
	if (!Array.isArray(arr)) return null
	const items: MusicDrumItem[] = []
	for (const el of arr) {
		if (el == null || typeof el !== 'object') continue
		const it = el as Record<string, unknown>
		const x = Math.round(Number(it.x))
		const y = Math.round(Number(it.y))
		const w = Math.max(0, Math.round(Number(it.w)))
		const h = Math.max(0, Math.round(Number(it.h)))
		if (![x, y, w, h].every(Number.isFinite)) continue
		const rawSim = it.similarity
		const similarity =
			rawSim != null && typeof rawSim !== 'object' ? Number(rawSim) : null
		items.push({
			key: String(it.key ?? ''),
			label: String(it.label ?? ''),
			x,
			y,
			w,
			h,
			similarity: similarity != null && Number.isFinite(similarity) ? similarity : null
		})
	}
	return { items }
}
