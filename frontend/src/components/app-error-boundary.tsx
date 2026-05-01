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
				<div className='flex h-full flex-col items-center justify-center gap-4 px-6 py-12 text-center'>
					<p className='text-sm font-medium text-slate-900'>页面渲染出错</p>
					<p className='max-w-md text-xs text-red-500'>{error.message}</p>
					{import.meta.env.DEV && error.stack && (
						<pre className='max-h-40 max-w-xl overflow-auto rounded-lg bg-slate-100 px-3 py-2 text-left font-mono text-[10px] whitespace-pre-wrap text-slate-600'>
							{error.stack}
						</pre>
					)}
					<button
						type='button'
						onClick={this.handleRetry}
						className='rounded-xl bg-white px-3 py-2 text-xs font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50'>
						重试
					</button>
				</div>
			)
		}
		return this.props.children
	}
}
