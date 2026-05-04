import { Button, Divider, Icon } from 'animal-island-ui'
import { useState } from 'react'
import { useAutoFishStatus } from '../hooks/use-auto-fish-status'
import { postAutoFishLogicState, type AutoFishLogicState } from '../lib/api-client'
import { AutoFishControls } from './auto-fish-controls'
import { FPS_MAX, FPS_MIN, MATCH_TH_MAX, MATCH_TH_MIN, useCaptureSession } from './capture-session-context'

const LOGIC_OPTIONS: { id: AutoFishLogicState; label: string }[] = [
	{ id: 'fishing', label: '钓鱼' },
	{ id: 'sell-fish', label: '卖鱼' },
	{ id: 'buy-bait', label: '买鱼饵' },
	{ id: 'change-bait', label: '换鱼饵' }
]

export function CaptureLeftPanel() {
	const { fps, setFps, matchTh, setMatchTh, applyCaptureSettings } = useCaptureSession()
	const busy = fps.saving || matchTh.saving
	const fish = useAutoFishStatus()
	const [logicBusy, setLogicBusy] = useState(false)
	const activeLogic = fish.status?.logic_state ?? 'fishing'

	const onPickLogic = async (id: AutoFishLogicState) => {
		if (id === activeLogic || logicBusy) return
		setLogicBusy(true)
		try {
			await postAutoFishLogicState(id)
			await fish.refresh()
		} catch (e) {
			console.error(e)
		} finally {
			setLogicBusy(false)
		}
	}

	return (
		<aside className='flex shrink-0 flex-col gap-3 overflow-y-auto'>
			<AutoFishControls fish={fish} />

			<div className='flex flex-col gap-1.5'>
				<div className='flex items-center gap-2'>
					<Icon name='icon-diy' size={18} bounce />
					<span className='text-xs font-medium text-[#725d42]'>逻辑状态</span>
				</div>
				<div className='grid grid-cols-2 gap-1.5'>
					{LOGIC_OPTIONS.map(opt => {
						const on = opt.id === activeLogic
						return (
							<div
								key={opt.id}
								role='button'
								tabIndex={logicBusy ? -1 : 0}
								onClick={() => {
									if (!logicBusy) void onPickLogic(opt.id)
								}}
								onKeyDown={e => {
									if (logicBusy) return
									if (e.key === 'Enter' || e.key === ' ') {
										e.preventDefault()
										void onPickLogic(opt.id)
									}
								}}
								className={`cursor-pointer select-none rounded-md px-2 py-2 text-center text-xs font-medium transition-colors ${
									on
										? 'bg-[#c9a882] text-[#2a2218] shadow-[inset_0_-2px_0_rgba(0,0,0,0.12)]'
										: 'bg-[#ebe4d6] text-[#4a3d2e] hover:bg-[#e0d8c8]'
								} ${logicBusy ? 'pointer-events-none opacity-60' : ''}`}
							>
								{opt.label}
							</div>
						)
					})}
				</div>
			</div>

			<Divider type='line-brown' />

			<div className='flex items-center gap-2'>
				<Icon name='icon-diy' size={20} bounce />
				<span className='text-sm font-medium'>配置</span>
			</div>

			<div className='grid grid-cols-2 gap-3'>
				<div className='flex flex-col gap-1'>
					<label htmlFor='capture-fps' className='text-xs font-medium text-[#725d42]'>
						帧率（FPS）: {fps.draft}
					</label>
					<input
						id='capture-fps'
						type='range'
						min={FPS_MIN}
						max={FPS_MAX}
						value={fps.draft}
						onChange={e => setFps(f => ({ ...f, draft: Number(e.target.value) }))}
						className='w-full accent-[#725d42]'
					/>
				</div>
				<div className='flex flex-col gap-1'>
					<label htmlFor='capture-match-th' className='text-xs font-medium text-[#725d42]'>
						页面匹配阈值（0–1）: {matchTh.draft.toFixed(2)}
					</label>
					<input
						id='capture-match-th'
						type='range'
						min={MATCH_TH_MIN}
						max={MATCH_TH_MAX}
						step={0.1}
						value={matchTh.draft}
						onChange={e => setMatchTh(m => ({ ...m, draft: Number(e.target.value) }))}
						className='w-full accent-[#725d42]'
					/>
				</div>
			</div>

			<Button type='primary' block size='small' htmlType='button' loading={busy} disabled={busy} onClick={() => void applyCaptureSettings()}>
				应用
			</Button>
		</aside>
	)
}
