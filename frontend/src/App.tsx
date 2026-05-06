import clsx from 'clsx'
import { useEffect, useState } from 'react'
import { postCaptureContext } from './lib/api-client'
import { AppErrorBoundary } from './components/app-error-boundary'
import { CaptureLeftPanel } from './components/capture-left-panel'
import { CaptureRightPanel } from './components/capture-right-panel'
import { CaptureSessionProvider, useCaptureSession } from './components/capture-session-context'
import AppTitleBar from './components/app-title-bar'
import type { WorkspaceTabId } from './components/workspace-types'
import { IconFish } from './components/icons/icon-fish'
import BgPattern from './components/ui/bg-pattern'

function AppWorkspaceShell() {
	const [workspace, setWorkspace] = useState<WorkspaceTabId>('fish')
	const { refreshCapture } = useCaptureSession()

	useEffect(() => {
		void (async () => {
			try {
				await postCaptureContext(workspace)
				await refreshCapture({ syncMatchThreshold: true })
			} catch (err) {
				console.error(err)
			}
		})()
	}, [workspace, refreshCapture])

	return (
		<div className='relative mx-12 mt-6'>
			<div className='absolute top-0 left-0 flex gap-2 px-16'>
				<div
					className={clsx('tab', workspace === 'fish' && 'active')}
					onClick={() => setWorkspace('fish')}
					role='tab'
					tabIndex={0}
					onKeyDown={e => {
						if (e.key === 'Enter' || e.key === ' ') setWorkspace('fish')
					}}>
					钓鱼
				</div>
				<div
					className={clsx('tab', workspace === 'music' && 'active')}
					onClick={() => setWorkspace('music')}
					role='tab'
					tabIndex={0}
					onKeyDown={e => {
						if (e.key === 'Enter' || e.key === ' ') setWorkspace('music')
					}}>
					超强音
				</div>
				<div
					className={clsx('tab', workspace === 'manager' && 'active')}
					onClick={() => setWorkspace('manager')}
					role='tab'
					tabIndex={0}
					onKeyDown={e => {
						if (e.key === 'Enter' || e.key === ' ') setWorkspace('manager')
					}}>
					店长特供
				</div>
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
				<CaptureLeftPanel workspace={workspace} />
				<CaptureRightPanel />
			</main>
		</div>
	)
}

function App() {
	return (
		<div className='bg-bg text-primary flex h-screen flex-col overflow-hidden'>
			<BgPattern />

			<div
				className='absolute inset-0'
				style={{
					backgroundImage: 'repeating-linear-gradient(-45deg, #ffffff05 0 2px, #34579c66 2px 4px)'
				}}></div>

			<div className='relative'>
				<AppTitleBar />
				<AppErrorBoundary>
					<CaptureSessionProvider>
						<AppWorkspaceShell />
					</CaptureSessionProvider>
				</AppErrorBoundary>
			</div>
		</div>
	)
}

export default App
