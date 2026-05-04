export type ReelingBarItem = {
	key: string
	label: string
	similarity: number | null
	x?: number
	y?: number
	w?: number
	h?: number
}

export type ReelingBarDebug = {
	match_ms: number
	items: ReelingBarItem[]
}

export function parseReelingBarDebug(raw: unknown): ReelingBarDebug | null {
	if (raw == null || typeof raw !== 'object') return null
	const o = raw as Record<string, unknown>
	const ms = Number(o.match_ms)
	if (!Number.isFinite(ms)) return null
	const itemsRaw = o.items
	if (!Array.isArray(itemsRaw)) return null
	const items: ReelingBarItem[] = []
	for (const it of itemsRaw) {
		if (it == null || typeof it !== 'object') continue
		const r = it as Record<string, unknown>
		const key = String(r.key ?? '')
		const label = String(r.label ?? '')
		const rawSim = r.similarity
		const similarity = rawSim == null || rawSim === '' ? null : Number(rawSim)
		const x = r.x != null ? Math.round(Number(r.x)) : undefined
		const y = r.y != null ? Math.round(Number(r.y)) : undefined
		const w = r.w != null ? Math.max(0, Math.round(Number(r.w))) : undefined
		const h = r.h != null ? Math.max(0, Math.round(Number(r.h))) : undefined
		items.push({
			key,
			label,
			similarity: similarity != null && Number.isFinite(similarity) ? similarity : null,
			x: x != null && Number.isFinite(x) ? x : undefined,
			y: y != null && Number.isFinite(y) ? y : undefined,
			w: w != null && Number.isFinite(w) ? w : undefined,
			h: h != null && Number.isFinite(h) ? h : undefined
		})
	}
	if (items.length === 0) return null
	return { match_ms: ms, items }
}
