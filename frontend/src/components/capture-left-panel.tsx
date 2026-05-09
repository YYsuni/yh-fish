import { RangeSlider } from './ui/range-slider'
import { Switch } from './ui/switch'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useAutoFishStatus } from '../hooks/use-auto-fish-status'
import { useMusicStatus } from '../hooks/use-music-status'
import { usePianoStatus } from '../hooks/use-piano-status'
import { useManagerStatus } from '../hooks/use-manager-status'
import { AutoFishControls } from './auto-fish/auto-fish-controls'
import { AutoFishSettings } from './auto-fish/auto-fish-settings'
import { IconSettings } from './icons/icon-settings'
import { AppSettingsModal } from './app-settings/app-settings-modal'
import { MusicSettings } from './music/music-settings'
import { PianoSettings } from './piano/piano-settings'
import { ManagerSettings } from './manager/manager-settings'
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
	const piano = usePianoStatus()
	const manager = useManagerStatus()
	const [settingsOpen, setSettingsOpen] = useState(false)

	return (
		<aside className='card col-span-2 flex flex-col'>
			<div className='card-title flex items-center justify-between gap-3'>
				<h2>运行配置</h2>
				<button
					type='button'
					aria-label='设置'
					className='rounded-xl border border-black/30 bg-white/25 p-2 text-black/70 hover:bg-white/35'
					onClick={() => setSettingsOpen(true)}>
					<IconSettings className='h-4 w-4' />
				</button>
			</div>

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

				{workspace === 'fish' && (
					<>
						<AutoFishSettings fish={fish} />
						<AutoFishControls fish={fish} />
					</>
				)}

				{workspace === 'music' && <MusicSettings music={music} />}

				{workspace === 'piano' && <PianoSettings piano={piano} />}

				{workspace === 'manager' && <ManagerSettings manager={manager} />}
			</div>

			<AppSettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
		</aside>
	)
}
