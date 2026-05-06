import { useState } from 'react'
import clsx from 'clsx'
import type { AutoFishLogicState } from '../../lib/api-client'
import { postAutoFishLogicState } from '../../lib/api-client'
import type { AutoFishRemote } from './auto-fish-controls'

const OPTIONS: { value: AutoFishLogicState; label: string }[] = [
	{ value: 'fishing', label: '钓鱼' },
	{ value: 'sell-fish', label: '卖鱼' },
	{ value: 'bait', label: '鱼饵' }
]

export function AutoFishLogicStatePicker({ fish }: { fish: AutoFishRemote }) {
	const logicState = fish.status?.logic_state ?? 'fishing'
	const [busy, setBusy] = useState(false)

	return (
		<div>
			<div className='mb-1.5 text-xs text-[#725d42]/90'>执行逻辑</div>
			<div className='flex gap-1.5'>
				{OPTIONS.map(({ value, label }) => {
					const active = logicState === value
					return (
						<button
							key={value}
							type='button'
							disabled={busy}
							className={clsx(
								'flex-1 rounded-lg border py-1.5 text-xs font-medium transition-colors',
								active ? 'bg-brand/20 border-black/45 text-[#725d42]' : 'border-black/15 bg-white/35 text-black/55 hover:bg-white/55'
							)}
							onClick={async () => {
								if (active) return
								setBusy(true)
								try {
									await postAutoFishLogicState(value)
									await fish.refresh()
								} catch (e) {
									console.error(e)
								} finally {
									setBusy(false)
								}
							}}>
							{label}
						</button>
					)
				})}
			</div>
		</div>
	)
}
