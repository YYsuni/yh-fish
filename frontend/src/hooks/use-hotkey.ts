import { useEffect, useRef } from 'react'
import type { Hotkey } from '../lib/hotkeys'
import { hotkeyEquals, hotkeyFromKeyboardEvent, isHotkeyEmpty, isModifierKey } from '../lib/hotkeys'

function isEditableTarget(target: EventTarget | null): boolean {
	if (!(target instanceof HTMLElement)) return false
	const tag = target.tagName.toLowerCase()
	if (tag === 'input' || tag === 'textarea' || tag === 'select') return true
	if (target.isContentEditable) return true
	return false
}

export function useHotkey(hotkey: Hotkey, handler: () => void, enabled = true) {
	const handlerRef = useRef(handler)
	handlerRef.current = handler

	const hotkeyRef = useRef(hotkey)
	hotkeyRef.current = hotkey

	useEffect(() => {
		if (!enabled) return
		if (typeof window === 'undefined') return

		const onKeyDown = (e: KeyboardEvent) => {
			if (e.repeat) return
			if (isEditableTarget(e.target)) return
			if (isHotkeyEmpty(hotkeyRef.current)) return
			if (isModifierKey(e.key)) return

			const cur = hotkeyFromKeyboardEvent(e)
			if (hotkeyEquals(cur, hotkeyRef.current)) {
				e.preventDefault()
				e.stopPropagation()
				handlerRef.current()
			}
		}

		window.addEventListener('keydown', onKeyDown, { capture: true })
		return () => window.removeEventListener('keydown', onKeyDown, { capture: true } as never)
	}, [enabled])
}

