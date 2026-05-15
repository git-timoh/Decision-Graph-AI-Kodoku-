#!/usr/bin/env node
/**
 * Regenerate `lib/types/contracts.ts` from the running backend's OpenAPI spec.
 *
 * Usage:
 *   1. Start the backend: `uvicorn kodoku.main:app --port 8000`
 *   2. From `frontend/`: `npm run gen:contracts`
 *   3. Commit the diff to `lib/types/contracts.ts`.
 *
 * In M6 this becomes a CI check that fails when contracts drift.
 */
import { writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import openapiTS, { astToString } from "openapi-typescript";

const BACKEND = process.env.KODOKU_BACKEND_URL ?? "http://localhost:8000";
const OUTPUT = resolve(process.cwd(), "lib/types/contracts.ts");

const HEADER = `/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Regenerate with: \`npm run gen:contracts\` (backend must be running on
 * \${KODOKU_BACKEND_URL:-http://localhost:8000}).
 */
/* eslint-disable */

`;

const url = new URL("/openapi.json", BACKEND).toString();
console.log(`Fetching OpenAPI schema from ${url}…`);

const ast = await openapiTS(new URL(url));
const body = astToString(ast);
await writeFile(OUTPUT, HEADER + body, "utf8");
console.log(`Wrote ${OUTPUT}`);
