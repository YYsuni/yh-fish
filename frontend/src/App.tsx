import { AppErrorBoundary } from './components/app-error-boundary'
import { CaptureLeftPanel } from './components/capture-left-panel'
import { CaptureRightPanel } from './components/capture-right-panel'
import { CaptureSessionProvider } from './components/capture-session-context'
import AppTitleBar from './components/app-title-bar'

function App() {
	return (
		<div
			className='bg-bg text-primary flex min-h-screen flex-col'
			style={{
				backgroundImage: 'repeating-linear-gradient(-45deg, #ffffff05 0 3px, transparent 3px 6px)'
			}}>
			<AppTitleBar />
			<AppErrorBoundary>
				<CaptureSessionProvider>
					<div className='relative mx-12 mt-6'>
						<div className='absolute top-0 left-0 flex gap-2 px-16'>
							<div className='tab active'>钓鱼</div>
							<div className='tab'>超强音</div>
						</div>

						<main
							className='relative z-10 grid grid-cols-5 gap-6 rounded-3xl border-2 border-black p-6 ring-3 ring-[#333]/40'
							style={{
								backgroundColor: '#333333',
								backgroundImage: 'radial-gradient(rgba(0, 0, 0, 0.12) 1px, transparent 1px), radial-gradient(rgba(0, 0, 0, 0.12) 1px, transparent 1px)',
								backgroundSize: '10px 10px',
								backgroundPosition: '0 0, 5px 5px',
								boxShadow: '0 0 4px 2px rgba(255, 255, 255, 0.2) inset, 0 0 20px 0 rgba(255, 255, 255, 0.1)'
							}}>
							<CaptureLeftPanel />
							<CaptureRightPanel />
						</main>
					</div>
				</CaptureSessionProvider>
			</AppErrorBoundary>
		</div>
	)
}

export default App
