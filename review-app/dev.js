import { spawn } from "node:child_process";

const commands = [
  ["api", "node", ["server.js"], { PORT: "8787" }],
  ["web", "vite", ["--host", "127.0.0.1"], {}]
];

const children = commands.map(([name, command, args, env]) => {
  const child = spawn(command, args, {
    shell: true,
    stdio: "inherit",
    env: { ...process.env, ...env }
  });
  child.on("exit", (code) => {
    if (code !== 0) {
      console.error(`${name} exited with code ${code}`);
      shutdown();
    }
  });
  return child;
});

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

function shutdown() {
  for (const child of children) {
    if (!child.killed) child.kill();
  }
  process.exit();
}
