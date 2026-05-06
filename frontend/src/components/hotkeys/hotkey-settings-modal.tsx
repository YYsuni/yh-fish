import { useEffect, useMemo, useState } from 'react'
import type { Hotkey, HotkeyId } from '../../lib/hotkeys'
import { emitHotkeysUpdated, formatHotkey } from '../../lib/hotkeys'
import { getHotkeys, postHotkeys } from '../../lib/api-client'
import { HotkeyCaptureModal } from './hotkey-capture-modal'
import { Modal } from '../ui/modal'

function displayName(id: HotkeyId): string {
	if (id === 'start') return '启动快捷键'
	return '停止快捷键'
}

export function HotkeySettingsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
	const [version, setVersion] = useState(0)
	const [captureId, setCaptureId] = useState<HotkeyId | null>(null)
	const [captureInitial, setCaptureInitial] = useState<Hotkey>({ key: null, ctrl: false, shift: false, alt: false, meta: false })
	const [hotkeysRemote, setHotkeysRemote] = useState<Record<HotkeyId, Hotkey>>({
		start: { key: null, ctrl: false, shift: false, alt: false, meta: false },
		stop: { key: 'F12', ctrl: false, shift: false, alt: false, meta: false }
	})

	useEffect(() => {
		if (!open) return
		void (async () => {
			try {
				const hk = await getHotkeys()
				setHotkeysRemote(hk)
			} catch (e) {
				console.error(e)
			}
		})()
	}, [open, version])

	const hotkeys = useMemo(() => {
		return hotkeysRemote
	}, [hotkeysRemote])

	const openCapture = (id: HotkeyId) => {
		setCaptureId(id)
		setCaptureInitial(hotkeys[id])
	}

	return (
		<>
			<Modal open={open} title='设置' onClose={onClose} maxWidthClassName='max-w-md'>
				<div className='space-y-3'>
					<div className='space-y-2'>
						{(['start', 'stop'] as const).map(id => (
							<button
								key={id}
								type='button'
								className='w-full rounded-2xl border-2 border-black/40 bg-white/25 px-4 py-3 text-left hover:bg-white/35'
								onClick={() => openCapture(id)}>
								<div className='flex items-center justify-between gap-3'>
									<div className='text-sm font-bold text-[#725d42]'>{displayName(id)}</div>
									<div className='rounded-xl border border-black/20 bg-white/35 px-2 py-1 text-xs font-semibold text-black/70'>{formatHotkey(hotkeys[id])}</div>
								</div>
							</button>
						))}
					</div>
				</div>
			</Modal>

			{captureId != null ? (
				<HotkeyCaptureModal
					open={captureId != null}
					id={captureId}
					initialValue={captureInitial}
					onCancel={() => setCaptureId(null)}
					onConfirm={next => {
						void (async () => {
							try {
								const merged = { ...hotkeysRemote, [captureId]: next }
								await postHotkeys(merged)
								setHotkeysRemote(merged)
								emitHotkeysUpdated(merged)
							} catch (e) {
								console.error(e)
							} finally {
								setCaptureId(null)
								setVersion(v => v + 1)
							}
						})()
					}}
				/>
			) : null}
		</>
	)
}
