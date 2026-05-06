export type ManagerSupplyMatchItem = {
	key: string
	/** 模板逻辑名（后端硬编码识别时下发） */
	name?: string
	x: number
	y: number
	w: number
	h: number
	similarity: number | null
}

export type ManagerSupplyMatchDebug = {
	match_ms?: number
	items: ManagerSupplyMatchItem[]
}

export function parseManagerSupplyMatchDebug(raw: unknown): ManagerSupplyMatchDebug | null {
	if (raw == null || typeof raw !== 'object') return null
	const o = raw as Record<string, unknown>
	const arr = o.items
	if (!Array.isArray(arr)) return null
	const items: ManagerSupplyMatchItem[] = []
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
			...(typeof it.name === 'string' && it.name.trim() ? { name: it.name.trim() } : {}),
			x,
			y,
			w,
			h,
			similarity: similarity != null && Number.isFinite(similarity) ? similarity : null
		})
	}
	const match_ms = o.match_ms != null ? Number(o.match_ms) : undefined
	return {
		items,
		...(match_ms != null && Number.isFinite(match_ms) ? { match_ms } : {})
	}
}
