export type Hotkey = {
	key: string | null
	ctrl: boolean
	shift: boolean
	alt: boolean
	meta: boolean
}

export type HotkeyId = 'start' | 'stop'

const STORAGE_KEY = 'yh-fish.hotkeys.v1'

const DEFAULT_HOTKEYS: Record<HotkeyId, Hotkey> = {
	start: { key: null, ctrl: false, shift: false, alt: false, meta: false },
	stop: { key: 'F12', ctrl: false, shift: false, alt: false, meta: false }
}

function normalizeKey(key: string): string {
	if (key === ' ') return 'Space'
	if (key.length === 1) return key.toUpperCase()
	return key
}

export function formatHotkey(hk: Hotkey): string {
	if (hk.key == null || hk.key === '') return '未设置'
	const parts: string[] = []
	if (hk.ctrl) parts.push('Ctrl')
	if (hk.shift) parts.push('Shift')
	if (hk.alt) parts.push('Alt')
	if (hk.meta) parts.push('Meta')
	parts.push(normalizeKey(hk.key))
	return parts.join('+')
}

export function isHotkeyEmpty(hk: Hotkey): boolean {
	return hk.key == null || hk.key === ''
}

export function hotkeyFromKeyboardEvent(e: KeyboardEvent): Hotkey {
	return {
		key: normalizeKey(e.key),
		ctrl: e.ctrlKey,
		shift: e.shiftKey,
		alt: e.altKey,
		meta: e.metaKey
	}
}

export function isModifierKey(key: string): boolean {
	return key === 'Control' || key === 'Shift' || key === 'Alt' || key === 'Meta'
}

export function hotkeyEquals(a: Hotkey, b: Hotkey): boolean {
	return normalizeKey(a.key ?? '') === normalizeKey(b.key ?? '') && a.ctrl === b.ctrl && a.shift === b.shift && a.alt === b.alt && a.meta === b.meta
}

export function getHotkeys(): Record<HotkeyId, Hotkey> {
	if (typeof window === 'undefined') return DEFAULT_HOTKEYS
	try {
		const raw = window.localStorage.getItem(STORAGE_KEY)
		if (raw == null || raw === '') return DEFAULT_HOTKEYS
		const parsed = JSON.parse(raw) as Partial<Record<HotkeyId, Partial<Hotkey>>>
		return {
			start: { ...DEFAULT_HOTKEYS.start, ...(parsed.start ?? {}) },
			stop: { ...DEFAULT_HOTKEYS.stop, ...(parsed.stop ?? {}) }
		}
	} catch {
		return DEFAULT_HOTKEYS
	}
}

export function setHotkey(id: HotkeyId, hk: Hotkey) {
	if (typeof window === 'undefined') return
	const next = getHotkeys()
	next[id] = { ...hk, key: hk.key == null || hk.key === '' ? null : normalizeKey(hk.key) }
	window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
}

export function clearHotkey(id: HotkeyId) {
	setHotkey(id, { key: null, ctrl: false, shift: false, alt: false, meta: false })
}
