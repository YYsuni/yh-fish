import { MusicControls } from './music-controls'
import type { MusicRemote } from './music-controls'

export function MusicSettings({ music }: { music: MusicRemote }) {
	return (
		<>
			<MusicControls music={music} />
		</>
	)
}
