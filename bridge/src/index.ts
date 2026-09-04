/**
 * GLASSPOCKET bridge. Build Spec Section 08.
 *
 * Polls the mint queue in Snowflake, mints one compressed NFT receipt per
 * verified disbursement on Solana devnet, and writes the asset identifier
 * back. The signing key never touches the warehouse.
 *
 *   npm run start           poll continuously
 *   npm run once            drain the queue once and exit
 *
 * WHY A PUBLIC LEDGER BELONGS HERE
 *   A donor verifying a claim about a charity is verifying it against a
 *   record kept by the charity, or by a platform the charity pays, or by
 *   an application built by someone they have never met. Every one of
 *   those requires trust in an interested party. A compressed NFT receipt
 *   is a record that persists whether or not GLASSPOCKET exists, whether
 *   or not the operator stays honest, and whether or not the warehouse is
 *   later edited. That property is the only reason a chain is here, and it
 *   is a real property rather than a decorative one.
 *
 * RUN THE FULL BATCH ON SATURDAY AFTERNOON.
 *   Sunday's recording must touch nothing live. Section 09.
 */

import "dotenv/config";

import { mintReceipt, type MintContext } from "./mint.js";
import { SnowflakeBridge, type QueueRow } from "./snowflake.js";
import { loadUmi } from "./tree.js";

const BATCH_SIZE = Number(process.env.MINT_BATCH_SIZE ?? 50);
const POLL_MS = Number(process.env.MINT_POLL_MS ?? 4000);
const ONCE = process.argv.includes("--once");

let running = true;
process.on("SIGINT", () => {
  console.log("\nstopping after the current batch");
  running = false;
});

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `${name} is not set. Run "npm run tree" first and paste the printed ` +
        `addresses into bridge/.env.`,
    );
  }
  return value;
}

async function main(): Promise<void> {
  const umi = loadUmi();

  const ctx: MintContext = {
    umi,
    merkleTree: requireEnv("MERKLE_TREE_ADDRESS"),
    collectionMint: requireEnv("COLLECTION_MINT"),
    // The treasury holds the receipts. It is the tree authority wallet
    // unless a separate one is configured.
    leafOwner: process.env.TREASURY_ADDRESS ?? umi.identity.publicKey.toString(),
  };

  const snow = new SnowflakeBridge();
  await snow.connect();

  const pending = await snow.pendingCount();
  console.log(`connected. ${pending} rows pending.`);
  console.log(`tree ${ctx.merkleTree}`);
  console.log(`cluster devnet\n`);

  let minted = 0;
  let failed = 0;

  while (running) {
    const batch: QueueRow[] = await snow.claimBatch(BATCH_SIZE);

    if (batch.length === 0) {
      if (ONCE) break;
      await new Promise((r) => setTimeout(r, POLL_MS));
      continue;
    }

    for (const row of batch) {
      if (!running) break;
      try {
        const result = await mintReceipt(ctx, row);
        await snow.writeMintLog(row, result);
        minted += 1;
        if (minted % 10 === 0) {
          console.log(`minted ${minted}  latest ${result.assetId}`);
        }
      } catch (error) {
        // Never crash the loop. One bad row must not cost the batch.
        failed += 1;
        await snow.markFailed(row, error);
        console.warn(
          `failed ${row.disbursementId}: ` +
            (error instanceof Error ? error.message : String(error)),
        );
      }
    }

    if (ONCE && batch.length < BATCH_SIZE) break;
    await new Promise((r) => setTimeout(r, POLL_MS));
  }

  const remaining = await snow.pendingCount();
  console.log(`\nminted ${minted}, failed ${failed}, ${remaining} still pending`);
  console.log(
    "A deliberate subset of verified disbursements is left unminted so the " +
      "missing-receipt gap on Tab 06 is real rather than staged. That subset " +
      "is excluded when the queue is populated in sql/13, not here.",
  );

  await snow.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
