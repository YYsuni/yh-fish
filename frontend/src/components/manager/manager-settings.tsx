import { ManagerControls } from './manager-controls'
import type { ManagerRemote } from './manager-controls'

export function ManagerSettings({ manager }: { manager: ManagerRemote }) {
	return (
		<>
			<ManagerControls manager={manager} />
		</>
	)
}

