import { useEffect, useState } from 'react'

declare global {
	interface Window {
		pywebview?: {
			api?: {
				minimize_window: () => Promise<void>
				close_window: () => Promise<void>
			}
		}
	}
}

function usePywebviewWindowChrome(): boolean {
	const [ready, setReady] = useState(false)
	useEffect(() => {
		const sync = () => {
			const api = window.pywebview?.api
			if (api?.minimize_window && api?.close_window) setReady(true)
		}
		sync()
		window.addEventListener('pywebviewready', sync)
		return () => window.removeEventListener('pywebviewready', sync)
	}, [])
	return ready
}

export default function AppTitleBar() {
	const windowChrome = usePywebviewWindowChrome()

	return (
		<header className='flex shrink-0 items-center'>
			<div className='pywebview-drag-region flex-1 p-4'>
				<div
					className='flex w-22 items-center justify-center rounded-full bg-[#161416] px-6 py-2 text-sm font-bold text-[#DBDBDB] italic ring-2 ring-black'
					style={{ boxShadow: '0 0 5px 0 rgba(255, 255, 255, 0.5) inset', letterSpacing: '0.15em' }}>
					异环
				</div>
			</div>
			{windowChrome ? (
				<div className='flex shrink-0 gap-2 p-4'>
					<button
						type='button'
						className='h-8 w-8 rounded-full border-2 border-black/20 bg-black/40 font-bold text-white/40 ring-2 ring-white/5 transition-colors hover:bg-black/80 hover:text-white'
						style={{ boxShadow: '0 0 2px 0 rgba(255, 255, 255, 0.5) inset' }}
						aria-label='最小化'
						onClick={() => void window.pywebview?.api?.minimize_window?.()}>
						<span className='pb-0.5 text-lg leading-none'>−</span>
					</button>
					<button
						type='button'
						className='h-8 w-8 rounded-full border-2 border-black/20 bg-black/40 font-bold text-white/40 ring-2 ring-white/5 transition-colors hover:bg-black/80 hover:text-white'
						style={{ boxShadow: '0 0 2px 0 rgba(255, 255, 255, 0.5) inset' }}
						aria-label='关闭'
						onClick={() => void window.pywebview?.api?.close_window?.()}>
						<span className='text-base leading-none'>×</span>
					</button>
				</div>
			) : null}
		</header>
	)
}
