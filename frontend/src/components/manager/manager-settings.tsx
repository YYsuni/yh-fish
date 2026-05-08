import { useState } from 'react'
import { Switch } from '../ui/switch'
import { postManagerDirectKnock } from '../../lib/api-client'
import { ManagerControls } from './manager-controls'
import type { ManagerRemote } from './manager-controls'

export function ManagerSettings({ manager }: { manager: ManagerRemote }) {
	const directKnock = manager.status?.direct_knock ?? true
	const [directKnockBusy, setDirectKnockBusy] = useState(false)

	return (
		<>
			<div className='mb-3 flex flex-col gap-2'>
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
			</div>
			<ManagerControls manager={manager} />
		</>
	)
}
