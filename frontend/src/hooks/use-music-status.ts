import { useCallback, useEffect, useState } from 'react'
import { getMusicStatus, type MusicStatusResponse } from '../lib/api-client'

export function useMusicStatus(pollMs = 1500) {
	const [status, setStatus] = useState<MusicStatusResponse | null>(null)
	const [err, setErr] = useState<string | null>(null)

	const refresh = useCallback(async () => {
		try {
			const s = await getMusicStatus()
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
