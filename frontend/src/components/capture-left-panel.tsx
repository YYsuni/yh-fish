import { Button, Divider, Icon } from 'animal-island-ui'
import { AutoFishControls } from './auto-fish-controls'
import { FPS_MAX, FPS_MIN, MATCH_TH_MAX, MATCH_TH_MIN, useCaptureSession } from './capture-session-context'

export function CaptureLeftPanel() {
	const { fps, setFps, matchTh, setMatchTh, applyCaptureSettings } = useCaptureSession()
	const busy = fps.saving || matchTh.saving

	return (
		<aside className='flex shrink-0 flex-col gap-3 overflow-y-auto'>
			<AutoFishControls />

			<Divider type='line-brown' />

			<div className='flex items-center gap-2'>
				<Icon name='icon-diy' size={20} bounce />
				<span className='text-sm font-medium'>捕获</span>
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
