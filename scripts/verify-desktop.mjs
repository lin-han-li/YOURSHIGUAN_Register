import path from "node:path";

import { currentTarget, parseArgs, projectRoot, run } from "./_shared.mjs";

const args = parseArgs(process.argv.slice(2));
const target = args.target || currentTarget();

run("npx", ["pyright", "--project", "pyrightconfig.json"]);
run("python", ["-m", "py_compile", "yourshiguan_register.py"]);
run("node", [path.join(projectRoot, "scripts", "check-web-syntax.mjs")]);
run("python", [path.join(projectRoot, "scripts", "smoke-test.py")]);
run("python", ["yourshiguan_register.py", "--help"]);
run("node", [path.join(projectRoot, "scripts", "check-workflow.mjs")]);

console.log(`Desktop verification completed for ${target}.`);
