import { Button, Card } from 'animal-island-ui'
import { Component, type ErrorInfo, type ReactNode } from 'react'

type Props = {
	children: ReactNode
}

type State = {
	error: Error | null
}

export class AppErrorBoundary extends Component<Props, State> {
	state: State = { error: null }

	static getDerivedStateFromError(error: Error): State {
		return { error }
	}

	componentDidCatch(error: Error, info: ErrorInfo) {
		console.error('[AppErrorBoundary]', error, info.componentStack)
	}

	handleRetry = () => {
		this.setState({ error: null })
	}

	render() {
		const { error } = this.state
		if (error) {
			return (
				<div className='flex min-h-screen flex-col items-center justify-center gap-4 px-6 py-12 text-center'>
					<Card color='app-red' className='max-w-lg p-6'>
						<p className='text-sm font-medium'>页面渲染出错</p>
						<p className='mt-2 text-xs opacity-95'>{error.message}</p>
						{import.meta.env.DEV && error.stack && (
							<pre className='mt-3 max-h-40 max-w-xl overflow-auto rounded-lg bg-black/10 px-3 py-2 text-left font-mono text-[10px] whitespace-pre-wrap opacity-90'>
								{error.stack}
							</pre>
						)}
						<Button type='primary' className='mt-4' htmlType='button' onClick={this.handleRetry}>
							重试
						</Button>
					</Card>
				</div>
			)
		}
		return this.props.children
	}
}
