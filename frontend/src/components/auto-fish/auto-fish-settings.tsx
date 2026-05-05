import { useState } from 'react'
import { Switch } from '../ui/switch'
import { postAutoFishSellOnNoBait } from '../../lib/api-client'
import type { AutoFishRemote } from './auto-fish-controls'

export function AutoFishSettings({ fish }: { fish: AutoFishRemote }) {
	const sellFishOnNoBait = fish.status?.sell_fish_on_no_bait ?? true
	const [sellOnNoBaitBusy, setSellOnNoBaitBusy] = useState(false)

	return (
		<>
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
		</>
	)
}
