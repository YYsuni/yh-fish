import { useEffect, useMemo, useState } from 'react'
import type { Hotkey, HotkeyId } from '../../lib/hotkeys'
import { formatHotkey, isModifierKey } from '../../lib/hotkeys'
import { Modal } from '../ui/modal'

function displayName(id: HotkeyId): string {
	if (id === 'start') return '启动快捷键'
	return '停止快捷键'
}

function normalizeKey(key: string): string {
	if (key === ' ') return 'Space'
	if (key.length === 1) return key.toUpperCase()
	return key
}

export function HotkeyCaptureModal({
	open,
	id,
	initialValue,
	onCancel,
	onConfirm
}: {
	open: boolean
	id: HotkeyId
	initialValue: Hotkey
	onCancel: () => void
	onConfirm: (next: Hotkey) => void
}) {
	const [draft, setDraft] = useState<Hotkey>(initialValue)
	const [capturing, setCapturing] = useState(false)

	useEffect(() => {
		if (!open) return
		setDraft(initialValue)
		setCapturing(true)
	}, [open, initialValue])

	useEffect(() => {
		if (!open) return
		const onKeyDown = (e: KeyboardEvent) => {
			e.preventDefault()
			e.stopPropagation()

			if (e.key === 'Escape') {
				onCancel()
				return
			}

			if (e.key === 'Backspace' || e.key === 'Delete') {
				setDraft({ key: null, ctrl: false, shift: false, alt: false, meta: false })
				setCapturing(false)
				return
			}

			const modifiers = { ctrl: e.ctrlKey, shift: e.shiftKey, alt: e.altKey, meta: e.metaKey }

			if (isModifierKey(e.key)) {
				setDraft(prev => ({ ...prev, ...modifiers, key: prev.key }))
				return
			}

			setDraft({ key: normalizeKey(e.key), ...modifiers })
			setCapturing(false)
		}

		window.addEventListener('keydown', onKeyDown, { capture: true })
		return () => window.removeEventListener('keydown', onKeyDown, { capture: true } as never)
	}, [open, onCancel])

	return (
		<Modal open={open} title={`设置 · ${displayName(id)}`} onClose={onCancel} maxWidthClassName='max-w-md'>
			<div className='space-y-3'>
				<div className='px-4 py-3 text-center'>
					<div className='mt-1 text-xl font-bold text-[#725d42]'>{formatHotkey(draft)}</div>
					<div className='mt-3 text-[11px] font-medium text-black/55'>(支持 Ctrl/Shift/Alt/Meta，Backspace/Delete 可清空)</div>
				</div>

				<div className='flex items-center justify-end gap-2'>
					<button
						type='button'
						className='rounded-xl border-2 border-black/40 bg-white/25 px-3 py-2 text-xs font-bold text-black/70 hover:bg-white/35'
						onClick={onCancel}>
						取消
					</button>
					<button
						type='button'
						className='rounded-xl border-2 border-black/40 bg-[#FF9A41] px-3 py-2 text-xs font-bold text-black/80 hover:brightness-105'
						onClick={() => onConfirm(draft)}>
						确认
					</button>
				</div>
			</div>
		</Modal>
	)
}
