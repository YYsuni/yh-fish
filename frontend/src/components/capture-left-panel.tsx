import { RangeSlider } from './ui/range-slider'
import { Switch } from './ui/switch'
import { useCallback, useEffect, useRef } from 'react'
import { useAutoFishStatus } from '../hooks/use-auto-fish-status'
import { useMusicStatus } from '../hooks/use-music-status'
import { AutoFishControls } from './auto-fish/auto-fish-controls'
import { AutoFishSettings } from './auto-fish/auto-fish-settings'
import { MusicSettings } from './music/music-settings'
import { FPS_MAX, FPS_MIN, MATCH_TH_MAX, MATCH_TH_MIN, useCaptureSession } from './capture-session-context'
import type { WorkspaceTabId } from './workspace-types'

const CAPTURE_SETTINGS_DEBOUNCE_MS = 400

export function CaptureLeftPanel({ workspace }: { workspace: WorkspaceTabId }) {
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
	const music = useMusicStatus()

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
					<span>预览调试</span>
					<Switch size='small' checked={previewDebug} onChange={setPreviewDebug} />
				</div>

				{workspace === 'fish' ? <AutoFishSettings fish={fish} /> : null}

				{workspace === 'fish' ? <AutoFishControls fish={fish} /> : <MusicSettings music={music} />}
			</div>
		</aside>
	)
}
