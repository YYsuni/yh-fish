import { Cursor, Footer, Time } from 'animal-island-ui'
import { AppErrorBoundary } from './components/app-error-boundary'
import { CapturePreviewSection } from './components/capture-preview-section'

function App() {
	return (
		<AppErrorBoundary>
			<Cursor>
				<main className='flex flex-1 justify-center p-4'>
					<CapturePreviewSection />
				</main>
			</Cursor>
		</AppErrorBoundary>
	)
}

export default App
