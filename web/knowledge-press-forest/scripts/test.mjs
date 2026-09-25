import { mkdtempSync, readdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { resolve, join } from "node:path";
import { spawnSync } from "node:child_process";
import ts from "typescript";

// Compile into a disposable directory alongside dependencies. No extra test runtime.
const output = mkdtempSync(resolve("node_modules/.forest-tests-"));
try {
  writeFileSync(join(output, "package.json"), '{"type":"commonjs"}');
  for (const file of readdirSync("src/game").filter((f) => f.endsWith(".ts"))) {
    const { outputText } = ts.transpileModule(readFileSync(`src/game/${file}`, "utf8"), {
      compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
    });
    writeFileSync(join(output, file.replace(/\.ts$/, ".js")), outputText);
  }
  const tests = readdirSync("tests").filter((file) => file.endsWith(".test.mjs")).map((file) => `tests/${file}`);
  const result = spawnSync(process.execPath, ["--test", ...tests], {
    stdio: "inherit", env: { ...process.env, FOREST_TEST_BUILD: output },
  });
  process.exitCode = result.status ?? 1;
} finally {
  rmSync(output, { recursive: true, force: true });
}
