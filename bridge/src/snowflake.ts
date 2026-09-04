/**
 * Snowflake client for the bridge. Build Spec Sections 04B and 08.
 *
 * TRAP 02 / WHY THE ARROW POINTS THIS WAY
 *   Trial accounts have no external network access. Any attempt to create
 *   an external access integration or call out from a UDF fails with error
 *   509009. This is why the bridge is an outbound-polling Node process
 *   that reaches INTO Snowflake, rather than Snowflake reaching out to an
 *   RPC. Do not attempt to invert it.
 *
 *   The second reason is better than the first: a signing key has no
 *   business inside a data warehouse regardless of what the platform
 *   permits.
 *
 * The bridge connects with a role that can write to the ORACLE schema.
 * Do not reuse GP_ANALYST here; that role exists to be constrained.
 */

import fs from "node:fs";
import snowflake from "snowflake-sdk";

export interface QueueRow {
  queueId: string;
  disbursementId: string;
  programmeCode: string;
  amountBand: string;
  windowKey: string;
  orgHash: string;
}

export interface MintResult {
  disbursementId: string;
  assetId: string;
  signature: string;
  treeAddress: string;
  leafIndex: number;
  explorerUrl: string;
}

// The SDK logs a banner and, at higher levels, statement text. Keep it
// quiet: nothing about this process should print anything that could end
// up in a recording.
snowflake.configure({ logLevel: "ERROR" });

function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `${name} is not set. Copy .env.example to .env and fill it in. ` +
        `SNOWFLAKE_ACCOUNT has the shape orgname-accountname and is the ` +
        `single most commonly mistyped value in the whole build.`,
    );
  }
  return value;
}

export class SnowflakeBridge {
  private connection: snowflake.Connection | null = null;

  async connect(): Promise<void> {
    const options: Record<string, unknown> = {
      account: required("SNOWFLAKE_ACCOUNT"),
      username: required("SNOWFLAKE_USER"),
      role: process.env.SNOWFLAKE_ROLE ?? "ACCOUNTADMIN",
      warehouse: process.env.SNOWFLAKE_WAREHOUSE ?? "GP_WH",
      database: process.env.SNOWFLAKE_DATABASE ?? "GLASSPOCKET",
      schema: process.env.SNOWFLAKE_SCHEMA ?? "ORACLE",
    };

    // Prefer key-pair authentication. Multi-factor may be enforced on the
    // trial, and a password prompt in the middle of a batch mint on
    // Saturday afternoon is a bad way to lose an hour.
    const keyPath = process.env.SNOWFLAKE_PRIVATE_KEY_PATH;
    if (keyPath) {
      options.authenticator = "SNOWFLAKE_JWT";
      options.privateKey = fs.readFileSync(keyPath, "utf8");
    } else {
      options.password = required("SNOWFLAKE_PASSWORD");
    }

    this.connection = snowflake.createConnection(
      options as unknown as snowflake.ConnectionOptions,
    );
    await new Promise<void>((resolve, reject) => {
      this.connection!.connect((err) => (err ? reject(err) : resolve()));
    });
  }

  private execute<T = Record<string, unknown>>(
    sqlText: string,
    binds: unknown[] = [],
  ): Promise<T[]> {
    if (!this.connection) throw new Error("not connected");
    return new Promise((resolve, reject) => {
      this.connection!.execute({
        sqlText,
        binds: binds as snowflake.Binds,
        complete: (err, _stmt, rows) =>
          err ? reject(err) : resolve((rows ?? []) as T[]),
      });
    });
  }

  /**
   * Claim a batch atomically, so two bridge processes can never mint the
   * same disbursement twice.
   */
  async claimBatch(size: number): Promise<QueueRow[]> {
    await this.execute(
      `UPDATE ORACLE.MINT_QUEUE
          SET status = 'CLAIMED', claimed_at = CURRENT_TIMESTAMP()
        WHERE queue_id IN (
          SELECT queue_id FROM ORACLE.MINT_QUEUE
           WHERE status = 'PENDING'
           ORDER BY queue_id
           LIMIT ?
        )`,
      [size],
    );

    const rows = await this.execute<Record<string, string>>(
      `SELECT queue_id, disbursement_id, programme_code,
              amount_band, window_key, org_hash
         FROM ORACLE.MINT_QUEUE
        WHERE status = 'CLAIMED'
          AND claimed_at >= DATEADD('minute', -2, CURRENT_TIMESTAMP())
        ORDER BY queue_id
        LIMIT ?`,
      [size],
    );

    return rows.map((r) => ({
      queueId: r.QUEUE_ID,
      disbursementId: r.DISBURSEMENT_ID,
      programmeCode: r.PROGRAMME_CODE,
      amountBand: r.AMOUNT_BAND,
      windowKey: r.WINDOW_KEY,
      orgHash: r.ORG_HASH,
    }));
  }

  async writeMintLog(row: QueueRow, result: MintResult): Promise<void> {
    await this.execute(
      `INSERT INTO ORACLE.MINT_LOG
         (disbursement_id, asset_id, signature, tree_address,
          leaf_index, minted_at, explorer_url)
       VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP(), ?)`,
      [
        result.disbursementId,
        result.assetId,
        result.signature,
        result.treeAddress,
        result.leafIndex,
        result.explorerUrl,
      ],
    );

    await this.execute(
      `UPDATE ORACLE.MINT_QUEUE SET status = 'MINTED' WHERE queue_id = ?`,
      [row.queueId],
    );
  }

  /** Never crash the loop. A failed row is recorded and the batch moves on. */
  async markFailed(row: QueueRow, error: unknown): Promise<void> {
    const text = error instanceof Error ? error.message : String(error);
    await this.execute(
      `INSERT INTO ORACLE.MINT_FAILURES
         (queue_id, disbursement_id, error_text) VALUES (?, ?, ?)`,
      [row.queueId, row.disbursementId, text.slice(0, 900)],
    );
    await this.execute(
      `UPDATE ORACLE.MINT_QUEUE SET status = 'FAILED' WHERE queue_id = ?`,
      [row.queueId],
    );
  }

  async pendingCount(): Promise<number> {
    const rows = await this.execute<{ N: number }>(
      `SELECT COUNT(*) AS N FROM ORACLE.MINT_QUEUE WHERE status = 'PENDING'`,
    );
    return Number(rows[0]?.N ?? 0);
  }

  async close(): Promise<void> {
    if (!this.connection) return;
    await new Promise<void>((resolve) => this.connection!.destroy(() => resolve()));
    this.connection = null;
  }
}
