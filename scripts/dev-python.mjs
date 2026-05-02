import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const win = join(root, ".venv", "Scripts", "python.exe");
const unix = join(root, ".venv", "bin", "python");
const py = existsSync(win) ? win : unix;

if (!existsSync(py)) {
	console.error(
		`未找到 .venv。请在仓库根目录创建虚拟环境，例如: python -m venv .venv`,
	);
	console.error(`期望路径: ${win} 或 ${unix}`);
	process.exit(1);
}

const main = join(root, "python", "main.py");
const child = spawn(py, [main, "--dev"], { stdio: "inherit", cwd: root, shell: false });
child.on("exit", (code, signal) => {
	if (signal) process.kill(process.pid, signal);
	process.exit(code ?? 1);
});
