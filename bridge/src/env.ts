/**
 * Environment loading. One .env, at the repository root.
 *
 * The bridge runs with its working directory inside bridge/, so a bare
 * `import "dotenv/config"` would look for bridge/.env and quietly find
 * nothing. Keeping two .env files in a project that handles a signing key
 * is how a credential ends up in the wrong one, so this resolves the
 * repository root explicitly and loads a single file.
 *
 * bridge/.env is still read afterwards if it exists, so a local override
 * works, but it is not where secrets are expected to live.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import dotenv from "dotenv";

const HERE = path.dirname(fileURLToPath(import.meta.url));

/** Repository root, two levels above bridge/src. */
export const ROOT = path.resolve(HERE, "..", "..");

dotenv.config({ path: path.join(ROOT, ".env") });
dotenv.config({ path: path.join(ROOT, "bridge", ".env") });

/**
 * Resolve a path from .env against the repository root.
 *
 * SOLANA_KEYPAIR_PATH is written relative to the root, where the keypair
 * actually sits, but the bridge runs from bridge/. Resolving against the
 * root means the same value works from either directory.
 */
export function resolveFromRoot(value: string): string {
  if (path.isAbsolute(value)) return value;

  const candidates = [
    path.resolve(ROOT, value),
    path.resolve(process.cwd(), value),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return candidates[0];
}
