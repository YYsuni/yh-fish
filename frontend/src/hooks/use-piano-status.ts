import { useCallback, useEffect, useState } from 'react'
import { getPianoStatus, type PianoStatusResponse } from '../lib/api-client'

export function usePianoStatus(pollMs = 1500) {
	const [status, setStatus] = useState<PianoStatusResponse | null>(null)
	const [err, setErr] = useState<string | null>(null)

	const refresh = useCallback(async () => {
		try {
			const s = await getPianoStatus()
			setStatus(s)
			setErr(null)
		} catch (e) {
			setErr(e instanceof Error ? e.message : String(e))
		}
	}, [])

	useEffect(() => {
		void refresh()
		const id = window.setInterval(() => void refresh(), pollMs)
		return () => window.clearInterval(id)
	}, [refresh, pollMs])

	return { status, err, refresh }
}
