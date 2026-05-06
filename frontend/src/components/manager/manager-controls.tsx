import { useEffect, useState } from 'react'
import { useManagerStatus } from '../../hooks/use-manager-status'
import { getAppSettings, postManagerStart, postManagerStop } from '../../lib/api-client'
import type { Hotkey, Hotkeys } from '../../lib/hotkeys'
import { formatHotkey, HOTKEYS_UPDATED_EVENT } from '../../lib/hotkeys'

export type ManagerRemote = ReturnType<typeof useManagerStatus>

export function ManagerControls({ manager }: { manager: ManagerRemote }) {
	const { status, refresh } = manager
	const running = status?.running ?? false
	const [busy, setBusy] = useState(false)
	const [hotkeys, setHotkeys] = useState<{ start: Hotkey; stop: Hotkey }>({
		start: { key: null, ctrl: false, shift: false, alt: false, meta: false },
		stop: { key: 'F12', ctrl: false, shift: false, alt: false, meta: false }
	})

	useEffect(() => {
		void (async () => {
			try {
				const s = await getAppSettings()
				setHotkeys({ start: s.start, stop: s.stop })
			} catch (e) {
				console.error(e)
			}
		})()
	}, [])

	useEffect(() => {
		const onUpdated = (e: Event) => {
			const next = (e as CustomEvent<Hotkeys>).detail
			if (next?.start && next?.stop) setHotkeys(next)
		}
		window.addEventListener(HOTKEYS_UPDATED_EVENT, onUpdated as EventListener)
		return () => window.removeEventListener(HOTKEYS_UPDATED_EVENT, onUpdated as EventListener)
	}, [])

	const onStart = async () => {
		setBusy(true)
		try {
			await postManagerStart()
			await refresh()
		} catch (e) {
			console.error(e)
		} finally {
			setBusy(false)
		}
	}

	const onStop = async () => {
		setBusy(true)
		try {
			await postManagerStop()
			await refresh()
		} catch (e) {
			console.error(e)
		} finally {
			setBusy(false)
		}
	}

	const lastPage = status?.last_page_id

	return (
		<section className='mt-auto'>
			<div className='mb-1.5 flex justify-center'>
				<span>运行状态：</span>
				<div className='text-xs font-medium text-[#725d42]'>{running ? '运行中' : '已停止'}</div>
			</div>

			<button className='brand-btn w-full' onClick={running ? onStop : onStart} disabled={busy}>
				{running ? (
					<>停止{hotkeys.stop.key && <span className='text-xs text-black/50'>（{formatHotkey(hotkeys.stop)}）</span>}</>
				) : (
					<>启动{hotkeys.start.key && <span className='text-xs text-black/50'>（{formatHotkey(hotkeys.start)}）</span>}</>
				)}
			</button>
		</section>
	)
}
