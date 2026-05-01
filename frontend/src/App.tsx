import { AppErrorBoundary } from './components/app-error-boundary'
import { CapturePreviewSection } from './components/capture-preview-section'

function App() {
	return (
		<AppErrorBoundary>
			<div className='flex min-h-full w-full justify-center overflow-y-auto px-6 py-12'>
				<CapturePreviewSection />
			</div>
		</AppErrorBoundary>
	)
}

export default App
