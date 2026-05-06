import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const req = join(root, "python", "requirements.txt");
const win = join(root, ".venv", "Scripts", "python.exe");
const unix = join(root, ".venv", "bin", "python");
const py = existsSync(win) ? win : existsSync(unix) ? unix : null;

if (!py) {
	console.warn(
		"[postinstall] 已跳过 python/requirements.txt：未找到 .venv（可先执行 python -m venv .venv）",
	);
	process.exit(0);
}

const r = spawnSync(py, ["-m", "pip", "install", "-r", req], {
	stdio: "inherit",
	cwd: root,
	shell: false,
});
process.exit(r.status === null ? 1 : r.status);
