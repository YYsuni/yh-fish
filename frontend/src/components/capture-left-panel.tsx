import { RangeSlider } from './ui/range-slider'
import { Switch } from './ui/switch'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useAutoFishStatus } from '../hooks/use-auto-fish-status'
import { postAutoFishLogicState, postAutoFishSellOnNoBait, type AutoFishLogicState } from '../lib/api-client'
import { AutoFishControls } from './auto-fish-controls'
import { FPS_MAX, FPS_MIN, MATCH_TH_MAX, MATCH_TH_MIN, useCaptureSession } from './capture-session-context'

const CAPTURE_SETTINGS_DEBOUNCE_MS = 400

const LOGIC_OPTIONS: { id: AutoFishLogicState; label: string }[] = [
	{ id: 'fishing', label: '钓鱼' },
	{ id: 'sell-fish', label: '卖鱼' },
	{ id: 'bait', label: '鱼饵' }
]

export function CaptureLeftPanel() {
	const { fps, setFps, matchTh, setMatchTh, applyCaptureSettings, previewDebug, setPreviewDebug } = useCaptureSession()
	const applyCaptureSettingsRef = useRef(applyCaptureSettings)
	applyCaptureSettingsRef.current = applyCaptureSettings
	const applyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
	const scheduleDebouncedApply = useCallback(() => {
		if (applyTimerRef.current != null) clearTimeout(applyTimerRef.current)
		applyTimerRef.current = setTimeout(() => {
			applyTimerRef.current = null
			void applyCaptureSettingsRef.current()
		}, CAPTURE_SETTINGS_DEBOUNCE_MS)
	}, [])

	useEffect(() => {
		return () => {
			if (applyTimerRef.current != null) clearTimeout(applyTimerRef.current)
		}
	}, [])

	const fish = useAutoFishStatus()
	const [logicBusy, setLogicBusy] = useState(false)
	const [sellOnNoBaitBusy, setSellOnNoBaitBusy] = useState(false)
	const activeLogic = fish.status?.logic_state ?? 'fishing'
	const sellFishOnNoBait = fish.status?.sell_fish_on_no_bait ?? true

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
		<aside className='card col-span-2 flex flex-col'>
			<h2 className='card-title'>运行配置</h2>

			<div
				className='card-content flex flex-1 flex-col gap-4 pb-4 text-xs font-medium text-[#725d42]'
				style={{
					backgroundImage:
						'linear-gradient(to right, rgba(114, 93, 66, 0.08) 1px, transparent 1px), linear-gradient(to bottom, rgba(114, 93, 66, 0.08) 1px, transparent 1px)',
					backgroundSize: '18px 18px'
				}}>
				<div>
					<div className='mb-1.5 flex items-center justify-between'>
						<span>帧率（FPS）</span>
						<span>{fps.draft}</span>
					</div>
					<RangeSlider
						min={FPS_MIN}
						max={FPS_MAX}
						value={fps.draft}
						onChange={v => {
							setFps(f => ({ ...f, draft: v }))
							scheduleDebouncedApply()
						}}
					/>
				</div>
				<div>
					<div className='mb-1.5 flex items-center justify-between'>
						<span>匹配阈值（0–1）</span>
						<span>{matchTh.draft.toFixed(2)}</span>
					</div>
					<RangeSlider
						min={MATCH_TH_MIN}
						max={MATCH_TH_MAX}
						step={0.1}
						value={matchTh.draft}
						onChange={v => {
							setMatchTh(m => ({ ...m, draft: v }))
							scheduleDebouncedApply()
						}}
					/>
				</div>

				<div className='flex items-center justify-between'>
					<span>是否卖鱼</span>
					<Switch
						size='small'
						checked={sellFishOnNoBait}
						loading={sellOnNoBaitBusy}
						disabled={sellOnNoBaitBusy}
						onChange={async v => {
							setSellOnNoBaitBusy(true)
							try {
								await postAutoFishSellOnNoBait(v)
								await fish.refresh()
							} catch (e) {
								console.error(e)
							} finally {
								setSellOnNoBaitBusy(false)
							}
						}}
					/>
				</div>

				<p className='flex items-start gap-1 text-[10px]'>
					<svg
						className='mt-px size-3 shrink-0 text-[#725d42]/90'
						viewBox='0 0 24 24'
						fill='none'
						stroke='currentColor'
						strokeWidth='2'
						strokeLinecap='round'
						strokeLinejoin='round'
						aria-hidden>
						<circle cx='12' cy='12' r='10' />
						<path d='M12 8v4M12 16h.01' />
					</svg>
					<span>{`钓鱼 -> (无鱼饵) -> ${sellFishOnNoBait ? '一键卖鱼 -> ' : ''}鱼饵 -> 钓鱼`}</span>
				</p>

				<div className='flex items-center justify-between'>
					<span>预览调试</span>
					<Switch size='small' checked={previewDebug} onChange={setPreviewDebug} />
				</div>

				<AutoFishControls fish={fish} />
			</div>
		</aside>
	)
}
