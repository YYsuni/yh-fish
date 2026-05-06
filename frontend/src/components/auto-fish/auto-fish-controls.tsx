import { useState } from 'react'
import { useAutoFishStatus } from '../../hooks/use-auto-fish-status'
import { useHotkey } from '../../hooks/use-hotkey'
import { postAutoFishStart, postAutoFishStop } from '../../lib/api-client'
import { formatHotkey, getHotkeys } from '../../lib/hotkeys'

const LOGIC_LABEL: Record<string, string> = {
	fishing: '钓鱼',
	'sell-fish': '卖鱼',
	bait: '鱼饵'
}

export type AutoFishRemote = ReturnType<typeof useAutoFishStatus>

export function AutoFishControls({ fish }: { fish: AutoFishRemote }) {
	const { status, refresh } = fish
	const running = status?.running ?? false
	const logicState = status?.logic_state ?? 'fishing'
	const [busy, setBusy] = useState(false)
	const { start: startHotkey, stop: stopHotkey } = getHotkeys()

	const onStart = async () => {
		setBusy(true)
		try {
			await postAutoFishStart()
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
			await postAutoFishStop()
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

	return (
		<section className='mt-auto'>
			<div className='mb-1.5 flex justify-center'>
				<span>运行状态：</span>
				<div className='text-xs font-medium text-[#725d42]'>{running ? `运行中 · ${LOGIC_LABEL[logicState] ?? logicState}` : '已停止'}</div>
			</div>

			<button className='brand-btn w-full' onClick={running ? onStop : onStart} disabled={busy}>
				{running ? (
					<>停止 {stopHotkey.key && <span className='text-xs text-black/50'>（{formatHotkey(stopHotkey)}）</span>}</>
				) : (
					<>启动 {startHotkey.key && <span className='text-xs text-black/50'>（{formatHotkey(startHotkey)}）</span>}</>
				)}
			</button>
		</section>
	)
}
