import { useState } from 'react'
import { useAutoFishStatus } from '../hooks/use-auto-fish-status'
import { postAutoFishStart, postAutoFishStop } from '../lib/api-client'

const LOGIC_LABEL: Record<string, string> = {
	fishing: '钓鱼',
	'sell-fish': '卖鱼',
	bait: '鱼饵'
}

export type AutoFishRemote = ReturnType<typeof useAutoFishStatus>

export function AutoFishControls({ fish }: { fish: AutoFishRemote }) {
	const { status, err: pollErr, refresh } = fish
	const running = status?.running ?? false
	const logicState = status?.logic_state ?? 'fishing'
	const [busy, setBusy] = useState(false)
	const [err, setErr] = useState<string | null>(null)

	const mergedErr = err ?? pollErr

	const onStart = async () => {
		setBusy(true)
		setErr(null)
		try {
			await postAutoFishStart()
			await refresh()
		} catch (e) {
			setErr(e instanceof Error ? e.message : String(e))
		} finally {
			setBusy(false)
		}
	}

	const onStop = async () => {
		setBusy(true)
		setErr(null)
		try {
			await postAutoFishStop()
			await refresh()
		} catch (e) {
			setErr(e instanceof Error ? e.message : String(e))
		} finally {
			setBusy(false)
		}
	}

	return (
		<section className='mt-auto'>
			<div className='mb-1.5 flex justify-center'>
				<span>运行状态：</span>
				<div className='text-xs font-medium text-[#725d42]'>{running ? `运行中 · ${LOGIC_LABEL[logicState] ?? logicState}` : '已停止'}</div>
			</div>

			<button className='brand-btn w-full' onClick={running ? onStop : onStart} disabled={busy}>
				{running ? (
					<>
						停止<span className='text-xs text-black/50'>（F12）</span>
					</>
				) : (
					'启动'
				)}
			</button>
		</section>
	)
}
