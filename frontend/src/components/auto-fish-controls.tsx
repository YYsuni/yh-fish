import { Button, Card, Icon } from 'animal-island-ui'
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

	const statusLine = running ? `运行中 · ${LOGIC_LABEL[logicState] ?? logicState}` : '已停止'

	return (
		<section className='w-full'>
			<div className='mb-2 flex items-center gap-2'>
				<Icon name='icon-critterpedia' size={22} bounce />
				<span className='font-medium'>自动钓鱼</span>
			</div>

			<Card color='brown' className='p-2.5'>
				<div className='flex flex-wrap items-center justify-between gap-2'>
					<div className='min-w-0 flex-1 text-white'>
						<p className='text-xs font-medium'>
							执行状态 <span className='text-xs text-white/60'>（F12 停止）</span>
						</p>
						<p className='truncate font-mono text-xs leading-snug' title={statusLine}>
							{statusLine}
						</p>
					</div>
					<div className='flex shrink-0 gap-1.5'>
						<Button type='primary' size='small' htmlType='button' loading={busy && !running} disabled={busy || running} onClick={() => void onStart()}>
							启动
						</Button>
						<Button type='default' size='small' htmlType='button' loading={busy && running} disabled={busy || !running} onClick={() => void onStop()}>
							停止
						</Button>
					</div>
				</div>
				{mergedErr != null ? <p className='mt-2 text-xs text-[#b54a4a]'>{mergedErr}</p> : null}
			</Card>
		</section>
	)
}
