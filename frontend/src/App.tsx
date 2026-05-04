import { Cursor } from 'animal-island-ui'
import { AppErrorBoundary } from './components/app-error-boundary'
import { CaptureLeftPanel } from './components/capture-left-panel'
import { CaptureRightPanel } from './components/capture-right-panel'
import { CaptureSessionProvider } from './components/capture-session-context'

function App() {
	return (
		<AppErrorBoundary>
			<Cursor>
				<CaptureSessionProvider>
					<main className='mx-auto grid h-full w-[800px] grid-cols-2 gap-6 p-6'>
						<CaptureLeftPanel />
						<CaptureRightPanel />
					</main>
				</CaptureSessionProvider>
			</Cursor>
		</AppErrorBoundary>
	)
}

export default App
