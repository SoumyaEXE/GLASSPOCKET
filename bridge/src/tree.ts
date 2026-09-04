/**
 * One-time Merkle tree and collection creation. Build Spec Section 08.
 *
 *   npm run tree            create the tree and the collection
 *   npm run balance         check the wallet before you need it
 *
 * TREE PARAMETERS ARE IMMUTABLE AFTER CREATION.
 *   maxDepth 14 gives a capacity of 16,384 leaves, which comfortably
 *   exceeds demo volume. Oversize deliberately: there is no way to grow a
 *   tree later, and running out mid-demo is unrecoverable.
 *
 * FUND THE WALLET ON FRIDAY, NOT SATURDAY.
 *   Devnet faucet rate limits are real and will bite on the evening you
 *   need them. If the faucet refuses, use an alternative faucet and reduce
 *   the tree depth to 12. Fifteen minutes. Section 10.
 *
 * Write the printed addresses into .env as MERKLE_TREE_ADDRESS and
 * COLLECTION_MINT. Record them carefully; they cannot be recreated.
 */

import "dotenv/config";
import fs from "node:fs";

import { createUmi } from "@metaplex-foundation/umi-bundle-defaults";
import {
  createTree,
  mplBubblegum,
} from "@metaplex-foundation/mpl-bubblegum";
import {
  createNft,
  mplTokenMetadata,
} from "@metaplex-foundation/mpl-token-metadata";
import {
  generateSigner,
  keypairIdentity,
  percentAmount,
  type Umi,
} from "@metaplex-foundation/umi";

const MAX_DEPTH = 14;          // 16,384 leaves
const MAX_BUFFER_SIZE = 64;

export function loadUmi(): Umi {
  const rpc = process.env.SOLANA_RPC_URL;
  if (!rpc) {
    throw new Error(
      "SOLANA_RPC_URL is not set. It must be a DAS-enabled devnet endpoint, " +
        "for example a Helius devnet URL. The default public devnet endpoint " +
        "does not serve the Digital Asset Standard API and reads will fail.",
    );
  }

  const keypairPath = process.env.SOLANA_KEYPAIR_PATH;
  if (!keypairPath) throw new Error("SOLANA_KEYPAIR_PATH is not set");

  const umi = createUmi(rpc).use(mplBubblegum()).use(mplTokenMetadata());
  const secret = new Uint8Array(JSON.parse(fs.readFileSync(keypairPath, "utf8")));
  const keypair = umi.eddsa.createKeypairFromSecretKey(secret);
  return umi.use(keypairIdentity(keypair));
}

async function reportBalance(umi: Umi): Promise<number> {
  const balance = await umi.rpc.getBalance(umi.identity.publicKey);
  const sol = Number(balance.basisPoints) / 1e9;
  console.log(`wallet   ${umi.identity.publicKey}`);
  console.log(`balance  ${sol.toFixed(4)} SOL (devnet)`);
  return sol;
}

async function main(): Promise<void> {
  const umi = loadUmi();

  if (process.argv.includes("--balance")) {
    await reportBalance(umi);
    return;
  }

  const sol = await reportBalance(umi);
  if (sol < 0.5) {
    console.warn(
      "\nLow balance. Creating a depth-14 tree costs meaningful devnet SOL.\n" +
        "Airdrop now, well ahead of when you need it:\n" +
        "  solana airdrop 2 --url devnet\n" +
        "If the faucet rate limits you, use an alternative faucet or drop\n" +
        "MAX_DEPTH to 12. See Section 10.\n",
    );
  }

  // The collection. Receipts group under it in wallets and explorers,
  // which is what makes the ledger legible to somebody who did not build
  // it.
  console.log("\ncreating collection NFT...");
  const collectionMint = generateSigner(umi);
  await createNft(umi, {
    mint: collectionMint,
    name: "GLASSPOCKET Receipts",
    uri: process.env.COLLECTION_URI ?? "https://glasspocket.invalid/collection.json",
    sellerFeeBasisPoints: percentAmount(0),
    isCollection: true,
  }).sendAndConfirm(umi, { confirm: { commitment: "finalized" } });
  console.log(`COLLECTION_MINT=${collectionMint.publicKey}`);

  console.log("\ncreating merkle tree...");
  const merkleTree = generateSigner(umi);
  const builder = await createTree(umi, {
    merkleTree,
    maxDepth: MAX_DEPTH,
    maxBufferSize: MAX_BUFFER_SIZE,
    public: false,
  });
  await builder.sendAndConfirm(umi, { confirm: { commitment: "finalized" } });

  console.log(`MERKLE_TREE_ADDRESS=${merkleTree.publicKey}`);
  console.log(`\ncapacity ${2 ** MAX_DEPTH} leaves, depth ${MAX_DEPTH}`);
  console.log(
    "\nPaste both values into bridge/.env now. Tree parameters are " +
      "immutable and these addresses cannot be recreated.",
  );
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}
