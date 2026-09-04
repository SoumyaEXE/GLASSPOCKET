/**
 * Report what the authority needs before anything on chain can happen.
 *
 *   cd bridge && npm run fund
 *
 * Two numbers matter and they are easy to confuse:
 *   the AUTHORITY signs and pays, so it needs SOL,
 *   the TREASURY only receives receipts and never signs.
 */
import dotenv from "dotenv";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Connection, Keypair, PublicKey, LAMPORTS_PER_SOL,
         clusterApiUrl } from "@solana/web3.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
dotenv.config({ path: path.join(ROOT, ".env") });

// Enough for a depth-14 tree, a collection NFT and the queued mints.
const NEEDED = 0.5;
// devnet-pow claims its reward with a normal transaction, so the miner
// has to be able to pay a fee before it can earn anything.
const BOOTSTRAP = 0.01;

const rpc = process.env.SOLANA_RPC_URL || clusterApiUrl("devnet");
const conn = new Connection(rpc, "confirmed");

const keyPath = path.resolve(ROOT, process.env.SOLANA_KEYPAIR_PATH ?? "./authority.json");
const authority = Keypair.fromSecretKey(
  new Uint8Array(JSON.parse(fs.readFileSync(keyPath, "utf8"))),
).publicKey;

const sol = (await conn.getBalance(authority)) / LAMPORTS_PER_SOL;
console.log("authority (signs and pays)");
console.log(`  ${authority.toBase58()}`);
console.log(`  ${sol.toFixed(4)} SOL`);

const treasury = process.env.TREASURY_ADDRESS;
if (treasury && treasury !== authority.toBase58()) {
  const t = (await conn.getBalance(new PublicKey(treasury))) / LAMPORTS_PER_SOL;
  console.log("treasury (receives receipts, never signs)");
  console.log(`  ${treasury}`);
  console.log(`  ${t.toFixed(4)} SOL   <- funding this does NOT enable minting`);
}

console.log("");
if (sol >= NEEDED) {
  console.log(`ready. ${sol.toFixed(3)} SOL covers the tree, the collection and the mints.`);
  console.log("  cd bridge && npm run tree && npm run start");
} else if (sol >= BOOTSTRAP) {
  console.log(`enough to pay fees but not enough to build. Mine the rest:`);
  console.log("  cd bridge && npm run mine        # 0.02 SOL per solve, no rate limit");
} else {
  console.log(`the authority is empty and needs about ${BOOTSTRAP} SOL to start.`);
  console.log("");
  console.log("  devnet-pow cannot bootstrap it: claiming a mined reward is a");
  console.log("  normal transaction, so the miner must already afford a fee.");
  console.log("  Airdrops are rate limited by IP, not by address, so a fresh");
  console.log("  keypair does not get around it either.");
  console.log("");
  console.log("  Send ~0.05 SOL (devnet) to the authority address above, then:");
  console.log("    cd bridge && npm run mine     # tops up from a 1.4M SOL faucet");
  console.log("    npm run tree && npm run start");
}
