import { useState } from 'react'
import { useMusicStatus } from '../../hooks/use-music-status'
import { useHotkey } from '../../hooks/use-hotkey'
import { postMusicStart, postMusicStop } from '../../lib/api-client'
import { formatHotkey, getHotkeys } from '../../lib/hotkeys'

export type MusicRemote = ReturnType<typeof useMusicStatus>

export function MusicControls({ music }: { music: MusicRemote }) {
	const { status, refresh } = music
	const running = status?.running ?? false
	const [busy, setBusy] = useState(false)
	const { start: startHotkey, stop: stopHotkey } = getHotkeys()

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

	useHotkey(startHotkey, () => {
		if (busy) return
		if (!running) void onStart()
	})
	useHotkey(stopHotkey, () => {
		if (busy) return
		if (running) void onStop()
	})

	const lastPage = status?.last_page_id

	return (
		<section className='mt-auto'>
			<div className='mb-1.5 flex justify-center'>
				<span>运行状态：</span>
				<div className='text-xs font-medium text-[#725d42]'>{running ? `运行中${lastPage != null && lastPage !== '' ? ` · ${lastPage}` : ''}` : '已停止'}</div>
			</div>

			<button className='brand-btn w-full' onClick={running ? onStop : onStart} disabled={busy}>
				{running ? (
					<>停止{stopHotkey.key && <span className='text-xs text-black/50'>（{formatHotkey(stopHotkey)}）</span>}</>
				) : (
					<>启动{startHotkey.key && <span className='text-xs text-black/50'>（{formatHotkey(startHotkey)}）</span>}</>
				)}
			</button>
		</section>
	)
}
