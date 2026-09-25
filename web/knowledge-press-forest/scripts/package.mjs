import { mkdirSync, readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

mkdirSync("releases", { recursive: true });
const result = spawnSync(process.execPath, [process.env.npm_execpath, "pack", "--pack-destination", "releases", "--ignore-scripts"], { stdio: "inherit" });
if (result.status !== 0) process.exit(result.status ?? 1);
const { name, version } = JSON.parse(readFileSync("package.json", "utf8"));
console.log(`\nShare releases/${name}-${version}.tgz. Extract it and serve package/dist/ with any static web server.\nNo Node.js or Python backend is needed in production.`);
