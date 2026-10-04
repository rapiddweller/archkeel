#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { collect } from "./collect.js";
import { decodeRequest } from "./protocol.js";
try {
  process.stdout.write(JSON.stringify(collect(decodeRequest(readFileSync(0, "utf8")))) + "\n");
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : "collection failed"}\n`);
  process.exitCode = 1;
}
