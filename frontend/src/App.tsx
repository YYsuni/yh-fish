import { AppErrorBoundary } from './components/app-error-boundary'
import { CapturePreviewSection } from './components/capture-preview-section'

function App() {
	return (
		<AppErrorBoundary>
			<div className='flex min-h-full w-full justify-center overflow-y-auto p-4'>
				<CapturePreviewSection />
			</div>
		</AppErrorBoundary>
	)
}

export default App
