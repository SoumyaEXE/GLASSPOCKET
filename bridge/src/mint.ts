/**
 * Receipt metadata and the mint call. Build Spec Section 08.
 *
 * WHAT GOES ON CHAIN, AND WHAT MUST NOT
 *
 *   On:     programme code, amount BAND, delivery WINDOW, a salted hash of
 *           the organisation identifier, a schema version.
 *   Never:  beneficiary identifier, coordinates, organisation name, the
 *           exact amount, the exact timestamp.
 *
 * The rule to state in the write-up is: publish the claim, not the data. A
 * public ledger is permanent, and permanence plus personal data is a harm
 * that cannot be undone. buildReceiptMetadata below is the only place that
 * decides what leaves the warehouse, which is why it is short and why it
 * takes a typed row rather than a loose object.
 */

import {
  mintToCollectionV1,
  parseLeafFromMintToCollectionV1Transaction,
} from "@metaplex-foundation/mpl-bubblegum";
import { publicKey, type Umi } from "@metaplex-foundation/umi";
import { base58 } from "@metaplex-foundation/umi/serializers";

import type { MintResult, QueueRow } from "./snowflake.js";

const SCHEMA_VERSION = "glasspocket-receipt-1";
const EXPLORER = "https://explorer.solana.com";

export interface MintContext {
  umi: Umi;
  merkleTree: string;
  collectionMint: string;
  leafOwner: string;
}

/**
 * The receipt carries a claim, never a person.
 *
 * Note what is absent: there is no beneficiary field to forget to strip,
 * because the queue table in Snowflake does not carry one either. The
 * privacy property is enforced by the shape of ORACLE.MINT_QUEUE, and
 * acceptance check PRV-04 fails the build if a forbidden column is ever
 * added to it.
 */
export function buildReceiptMetadata(row: QueueRow) {
  return {
    name: `Receipt ${row.programmeCode} ${row.windowKey}`,
    symbol: "GPKT",
    uri: `https://glasspocket.invalid/receipt/${row.disbursementId}.json`,
    sellerFeeBasisPoints: 0,
    collection: undefined as unknown,
    creators: [],
    attributes: [
      { trait_type: "schema", value: SCHEMA_VERSION },
      { trait_type: "programme", value: row.programmeCode },
      { trait_type: "amount_band", value: row.amountBand },
      { trait_type: "window", value: row.windowKey },
      { trait_type: "org_hash", value: row.orgHash },
      { trait_type: "cluster", value: "devnet" },
    ],
  };
}

export function explorerUrl(assetId: string): string {
  return `${EXPLORER}/address/${assetId}?cluster=devnet`;
}

/**
 * Mint one receipt.
 *
 * OPERATIONAL RULES, SECTION 08
 *   Confirm at `finalized` commitment before parsing the asset identifier,
 *   or the parse fails intermittently. The DAS index lags the mint, so a
 *   read straight afterwards can 404; the application never depends on
 *   that read, because it serves the local mirror instead.
 */
export async function mintReceipt(
  ctx: MintContext,
  row: QueueRow,
): Promise<MintResult> {
  const metadata = buildReceiptMetadata(row);

  const { signature } = await mintToCollectionV1(ctx.umi, {
    leafOwner: publicKey(ctx.leafOwner),
    merkleTree: publicKey(ctx.merkleTree),
    collectionMint: publicKey(ctx.collectionMint),
    metadata: {
      name: metadata.name,
      symbol: metadata.symbol,
      uri: metadata.uri,
      sellerFeeBasisPoints: metadata.sellerFeeBasisPoints,
      collection: { key: publicKey(ctx.collectionMint), verified: false },
      creators: [],
    },
  }).sendAndConfirm(ctx.umi, { confirm: { commitment: "finalized" } });

  const leaf = await parseLeafFromMintToCollectionV1Transaction(
    ctx.umi,
    signature,
  );

  const assetId = leaf.id.toString();

  return {
    disbursementId: row.disbursementId,
    assetId,
    signature: base58.deserialize(signature)[0],
    treeAddress: ctx.merkleTree,
    leafIndex: Number(leaf.nonce),
    explorerUrl: explorerUrl(assetId),
  };
}

/**
 * Poll DAS until the asset is indexed.
 *
 * Only used by the verification pass. The interface never waits on this:
 * it reads ORACLE.MINT_LOG, so an indexing delay cannot stall a demo.
 */
export async function waitForIndex(
  umi: Umi,
  assetId: string,
  attempts = 8,
): Promise<boolean> {
  const { dasApi } = await import(
    "@metaplex-foundation/digital-asset-standard-api"
  );
  const api = umi.use(dasApi());

  for (let i = 0; i < attempts; i += 1) {
    try {
      await (api.rpc as unknown as {
        getAsset: (id: unknown) => Promise<unknown>;
      }).getAsset(publicKey(assetId));
      return true;
    } catch {
      await new Promise((r) => setTimeout(r, 1500 * 2 ** i));
    }
  }
  return false;
}
