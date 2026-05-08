import { useState } from 'react'
import { Switch } from '../ui/switch'
import { postManagerAutoSelectLevel, postManagerDirectKnock } from '../../lib/api-client'
import { ManagerControls } from './manager-controls'
import type { ManagerRemote } from './manager-controls'

export function ManagerSettings({ manager }: { manager: ManagerRemote }) {
	const directKnock = manager.status?.direct_knock ?? true
	const [directKnockBusy, setDirectKnockBusy] = useState(false)
	const autoSelectLevel = manager.status?.auto_select_level ?? true
	const [autoSelectLevelBusy, setAutoSelectLevelBusy] = useState(false)

	return (
		<>
			<div className='flex items-center justify-between'>
				<span>自动选关</span>
				<Switch
					size='small'
					checked={autoSelectLevel}
					loading={autoSelectLevelBusy}
					disabled={autoSelectLevelBusy}
					onChange={async v => {
						setAutoSelectLevelBusy(true)
						try {
							await postManagerAutoSelectLevel(v)
							await manager.refresh()
						} catch (e) {
							console.error(e)
						} finally {
							setAutoSelectLevelBusy(false)
						}
					}}
				/>
			</div>

			<div className='flex items-center justify-between'>
				<span>娜娜莉直接敲</span>
				<Switch
					size='small'
					checked={directKnock}
					loading={directKnockBusy}
					disabled={directKnockBusy}
					onChange={async v => {
						setDirectKnockBusy(true)
						try {
							await postManagerDirectKnock(v)
							await manager.refresh()
						} catch (e) {
							console.error(e)
						} finally {
							setDirectKnockBusy(false)
						}
					}}
				/>
			</div>

			{!directKnock && (
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
					<span>没有娜娜莉，只能打 1 ~ 8 关，效果并不好</span>
				</p>
			)}

			<ManagerControls manager={manager} />
		</>
	)
}
