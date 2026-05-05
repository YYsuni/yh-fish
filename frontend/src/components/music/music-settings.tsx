import { MusicControls } from './music-controls'
import type { MusicRemote } from './music-controls'

export function MusicSettings({ music }: { music: MusicRemote }) {
	return (
		<>
			{/* <p className='flex items-start gap-1 text-[10px]'>
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
				<span>
					页面识别使用 `images/music/page.json`；各页逻辑在 `music_executor.MUSIC_PAGE_HANDLERS` 中按 `id` 扩展。
				</span>
			</p> */}

			<MusicControls music={music} />
		</>
	)
}
