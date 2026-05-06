import { useEffect, useState } from 'react'
import { useMusicStatus } from '../../hooks/use-music-status'
import { postMusicStart, postMusicStop } from '../../lib/api-client'
import { getAppSettings } from '../../lib/api-client'
import type { Hotkey, Hotkeys } from '../../lib/hotkeys'
import { formatHotkey, HOTKEYS_UPDATED_EVENT } from '../../lib/hotkeys'

export type MusicRemote = ReturnType<typeof useMusicStatus>

export function MusicControls({ music }: { music: MusicRemote }) {
	const { status, refresh } = music
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
			await postMusicStart()
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
			await postMusicStop()
			await refresh()
		} catch (e) {
			console.error(e)
		} finally {
			setBusy(false)
		}
	}

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
