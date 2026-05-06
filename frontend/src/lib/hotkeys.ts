export type Hotkey = {
	key: string | null
	ctrl: boolean
	shift: boolean
	alt: boolean
	meta: boolean
}

export type HotkeyId = 'start' | 'stop'

export type Hotkeys = Record<HotkeyId, Hotkey>

export const HOTKEYS_UPDATED_EVENT = 'yh-fish:hotkeys-updated' as const

export function emitHotkeysUpdated(hotkeys: Hotkeys) {
	if (typeof window === 'undefined') return
	window.dispatchEvent(new CustomEvent<Hotkeys>(HOTKEYS_UPDATED_EVENT, { detail: hotkeys }))
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

export function isModifierKey(key: string): boolean {
	return key === 'Control' || key === 'Shift' || key === 'Alt' || key === 'Meta'
}

export function hotkeyEquals(a: Hotkey, b: Hotkey): boolean {
	return (
		normalizeKey(a.key ?? '') === normalizeKey(b.key ?? '') &&
		a.ctrl === b.ctrl &&
		a.shift === b.shift &&
		a.alt === b.alt &&
		a.meta === b.meta
	)
}
