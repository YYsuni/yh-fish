import { Button, Card, Icon } from 'animal-island-ui'
import { useCallback, useEffect, useState } from 'react'
import { getAutoFishStatus, postAutoFishStart, postAutoFishStop } from '../lib/api-client'

export function AutoFishControls() {
	const [running, setRunning] = useState(false)
	const [lastPageId, setLastPageId] = useState<string | null>(null)
	const [busy, setBusy] = useState(false)
	const [err, setErr] = useState<string | null>(null)

	const refresh = useCallback(async () => {
		try {
			const s = await getAutoFishStatus()
			setRunning(s.running)
			setLastPageId(s.last_page_id ?? null)
			setErr(null)
		} catch (e) {
			setErr(e instanceof Error ? e.message : String(e))
		}
	}, [])

	useEffect(() => {
		void refresh()
		const id = window.setInterval(() => void refresh(), 1500)
		return () => window.clearInterval(id)
	}, [refresh])

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

	const statusLine = running ? '运行中' : '已停止'

	return (
		<section className='w-full'>
			<div className='mb-2 flex items-center gap-2'>
				<Icon name='icon-critterpedia' size={22} bounce />
				<span className='font-medium'>自动钓鱼</span>
			</div>

			<Card color='brown' className='p-2.5'>
				<div className='flex flex-wrap items-center justify-between gap-2'>
					<div className='min-w-0 flex-1'>
						<p className='text-xs font-medium text-[#725d42]'>执行状态</p>
						<p className='truncate font-mono text-xs leading-snug text-[#4a3d2e]' title={statusLine}>
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
				{err != null ? <p className='mt-2 text-xs text-[#b54a4a]'>{err}</p> : null}
			</Card>
		</section>
	)
}
