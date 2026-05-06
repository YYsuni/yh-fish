import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Hotkey, HotkeyId } from '../../lib/hotkeys'
import { emitHotkeysUpdated, formatHotkey } from '../../lib/hotkeys'
import type { AppSettingsPayload } from '../../lib/api-client'
import { getAppSettings, postAppSettings } from '../../lib/api-client'
import { HotkeyCaptureModal } from './hotkey-capture-modal'
import { Modal } from '../ui/modal'

/** 与 `capture-left-panel` 中 `CAPTURE_SETTINGS_DEBOUNCE_MS` 一致 */
const CLICK_OFFSET_DEBOUNCE_MS = 400

function displayHotkeyName(id: HotkeyId): string {
	if (id === 'start') return '启动快捷键'
	return '停止快捷键'
}

function defaultAppSettings(): AppSettingsPayload {
	return {
		start: { key: null, ctrl: false, shift: false, alt: false, meta: false },
		stop: { key: 'F12', ctrl: false, shift: false, alt: false, meta: false },
		click_offset_x: 0,
		click_offset_y: 0
	}
}

function parseOffset(raw: string): number {
	const n = Number.parseInt(raw.trim(), 10)
	return Number.isFinite(n) ? n : 0
}

export function AppSettingsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
	const [version, setVersion] = useState(0)
	const [captureId, setCaptureId] = useState<HotkeyId | null>(null)
	const [captureInitial, setCaptureInitial] = useState<Hotkey>({ key: null, ctrl: false, shift: false, alt: false, meta: false })
	const [settingsRemote, setSettingsRemote] = useState<AppSettingsPayload>(defaultAppSettings)
	const [offsetXInput, setOffsetXInput] = useState('0')
	const [offsetYInput, setOffsetYInput] = useState('0')

	const settingsRemoteRef = useRef(settingsRemote)
	settingsRemoteRef.current = settingsRemote

	const offsetXDraftRef = useRef('0')
	const offsetYDraftRef = useRef('0')
	offsetXDraftRef.current = offsetXInput
	offsetYDraftRef.current = offsetYInput

	const persistTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
	/** 避免从未打开过设置时，挂载阶段 `open === false` 误用默认状态向后端写入 */
	const settingsModalWasOpenRef = useRef(false)

	const persistDraftOffsetsIfDirty = useCallback(async () => {
		const ox = parseOffset(offsetXDraftRef.current)
		const oy = parseOffset(offsetYDraftRef.current)
		const cur = settingsRemoteRef.current
		if (cur.click_offset_x === ox && cur.click_offset_y === oy) return
		try {
			const saved = await postAppSettings({ ...cur, click_offset_x: ox, click_offset_y: oy })
			settingsRemoteRef.current = saved
			setSettingsRemote(saved)
		} catch (e) {
			console.error(e)
		}
	}, [])

	const scheduleDebouncedPersistClickOffsets = useCallback(() => {
		if (persistTimerRef.current != null) clearTimeout(persistTimerRef.current)
		persistTimerRef.current = setTimeout(() => {
			persistTimerRef.current = null
			void persistDraftOffsetsIfDirty()
		}, CLICK_OFFSET_DEBOUNCE_MS)
	}, [persistDraftOffsetsIfDirty])

	useEffect(() => {
		return () => {
			if (persistTimerRef.current != null) clearTimeout(persistTimerRef.current)
		}
	}, [])

	useEffect(() => {
		if (!open) {
			if (persistTimerRef.current != null) {
				clearTimeout(persistTimerRef.current)
				persistTimerRef.current = null
			}
			if (settingsModalWasOpenRef.current) {
				settingsModalWasOpenRef.current = false
				void persistDraftOffsetsIfDirty()
			}
			return
		}
		settingsModalWasOpenRef.current = true
		void (async () => {
			try {
				const s = await getAppSettings()
				settingsRemoteRef.current = s
				setSettingsRemote(s)
				const sx = String(s.click_offset_x ?? 0)
				const sy = String(s.click_offset_y ?? 0)
				offsetXDraftRef.current = sx
				offsetYDraftRef.current = sy
				setOffsetXInput(sx)
				setOffsetYInput(sy)
			} catch (e) {
				console.error(e)
			}
		})()
	}, [open, version, persistDraftOffsetsIfDirty])

	const hotkeys = useMemo(() => ({ start: settingsRemote.start, stop: settingsRemote.stop }), [settingsRemote])

	const openCapture = (id: HotkeyId) => {
		setCaptureId(id)
		setCaptureInitial(hotkeys[id])
	}

	return (
		<>
			<Modal open={open} title='设置' onClose={onClose} maxWidthClassName='max-w-md'>
				<div className='space-y-2'>
					<div className='text-xs font-bold text-black/50'>快捷键</div>
					{(['start', 'stop'] as const).map(id => (
						<button
							key={id}
							type='button'
							className='w-full rounded-2xl border-2 border-black/40 bg-white/25 px-4 py-3 text-left hover:bg-white/35'
							onClick={() => openCapture(id)}>
							<div className='flex items-center justify-between gap-3'>
								<div className='text-sm font-bold text-[#725d42]'>{displayHotkeyName(id)}</div>
								<div className='rounded-xl border border-black/20 bg-white/35 px-2 py-1 text-xs font-semibold text-black/70'>{formatHotkey(hotkeys[id])}</div>
							</div>
						</button>
					))}

					<div className='mt-2 text-xs font-bold text-black/50'>其它</div>
					<div className='flex w-full items-center justify-between gap-2 rounded-2xl border-2 border-black/40 bg-white/25 px-4 py-3 hover:bg-white/35'>
						<div className='shrink-0 text-sm font-bold text-[#725d42]'>点击偏移</div>
						<div className='flex min-w-0 items-center gap-1.5'>
							<span className='shrink-0 text-[11px] font-semibold text-black/45'>X</span>
							<input
								type='text'
								inputMode='numeric'
								aria-label='点击偏移 X'
								className='w-16 min-w-0 rounded-lg border border-black/20 bg-white/35 px-1.5 py-0.5 text-center font-mono text-xs font-semibold text-black/70 outline-none focus:ring-2 focus:ring-black/15'
								value={offsetXInput}
								onChange={e => {
									const v = e.target.value
									setOffsetXInput(v)
									offsetXDraftRef.current = v
									scheduleDebouncedPersistClickOffsets()
								}}
							/>
							<span className='shrink-0 text-[11px] font-semibold text-black/45'>Y</span>
							<input
								type='text'
								inputMode='numeric'
								aria-label='点击偏移 Y'
								className='w-16 min-w-0 rounded-lg border border-black/20 bg-white/35 px-1.5 py-0.5 text-center font-mono text-xs font-semibold text-black/70 outline-none focus:ring-2 focus:ring-black/15'
								value={offsetYInput}
								onChange={e => {
									const v = e.target.value
									setOffsetYInput(v)
									offsetYDraftRef.current = v
									scheduleDebouncedPersistClickOffsets()
								}}
							/>
						</div>
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
								const merged: AppSettingsPayload = { ...settingsRemoteRef.current, [captureId]: next }
								const saved = await postAppSettings(merged)
								settingsRemoteRef.current = saved
								setSettingsRemote(saved)
								setOffsetXInput(String(saved.click_offset_x))
								setOffsetYInput(String(saved.click_offset_y))
								offsetXDraftRef.current = String(saved.click_offset_x)
								offsetYDraftRef.current = String(saved.click_offset_y)
								emitHotkeysUpdated({ start: saved.start, stop: saved.stop })
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
