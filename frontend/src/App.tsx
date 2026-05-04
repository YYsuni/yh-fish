import { Cursor } from 'animal-island-ui'
import { useEffect, useState } from 'react'
import { AppErrorBoundary } from './components/app-error-boundary'
import { CaptureLeftPanel } from './components/capture-left-panel'
import { CaptureRightPanel } from './components/capture-right-panel'
import { CaptureSessionProvider } from './components/capture-session-context'

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

function AppTitleBar({ showWindowControls }: { showWindowControls: boolean }) {
	const btnClass =
		'flex h-full w-11 items-center justify-center text-stone-300 transition-colors hover:bg-zinc-800 hover:text-stone-100 active:bg-zinc-950'

	return (
		<header className='flex h-10 shrink-0 items-stretch bg-zinc-900 text-stone-200'>
			<div className='pywebview-drag-region flex min-w-0 flex-1 items-center px-3 text-sm font-medium select-none'>
				<span className='truncate'>异环钓鱼工具</span>
			</div>
			{showWindowControls ? (
				<div className='flex shrink-0'>
					<button type='button' className={btnClass} aria-label='最小化' onClick={() => void window.pywebview?.api?.minimize_window?.()}>
						<span className='pb-0.5 text-lg leading-none'>−</span>
					</button>
					<button type='button' className={btnClass} aria-label='关闭' onClick={() => void window.pywebview?.api?.close_window?.()}>
						<span className='text-base leading-none'>×</span>
					</button>
				</div>
			) : null}
		</header>
	)
}

function App() {
	const windowChrome = usePywebviewWindowChrome()

	return (
		<div className='flex min-h-screen flex-col'>
			<AppTitleBar showWindowControls={windowChrome} />
			<AppErrorBoundary>
				<div className='flex min-h-0 min-w-0 flex-1 flex-col'>
					<Cursor>
						<CaptureSessionProvider>
							<main className='mx-auto grid min-h-0 w-[800px] flex-1 grid-cols-2 gap-6 overflow-auto p-6'>
								<CaptureLeftPanel />
								<CaptureRightPanel />
							</main>
						</CaptureSessionProvider>
					</Cursor>
				</div>
			</AppErrorBoundary>
		</div>
	)
}

export default App
