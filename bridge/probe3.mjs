import dotenv from "dotenv"; import path from "node:path"; import snowflake from "snowflake-sdk";
dotenv.config({ path: path.resolve("..", ".env") });
snowflake.configure({ logLevel: "OFF" });
const conn = snowflake.createConnection({
  account: process.env.SNOWFLAKE_ACCOUNT, username: process.env.SNOWFLAKE_USER,
  password: process.env.SNOWFLAKE_PASSWORD, role: process.env.SNOWFLAKE_ROLE });
const q = (sql) => new Promise((res, rej) =>
  conn.execute({ sqlText: sql, complete: (e, s, rows) => e ? rej(e) : res(rows) }));

conn.connect(async (err) => {
  if (err) { console.log("CONNECT FAILED", err.message); process.exit(1); }
  try {
    await q("CREATE DATABASE IF NOT EXISTS GP_PROBE2");
    await q("CREATE SCHEMA IF NOT EXISTS GP_PROBE2.S");
    const tests = [
      ["AGGREGATION POLICY", "CREATE OR REPLACE AGGREGATION POLICY GP_PROBE2.S.AP AS () RETURNS AGGREGATION_CONSTRAINT -> AGGREGATION_CONSTRAINT(MIN_GROUP_SIZE => 50)"],
      ["MASKING POLICY",     "CREATE OR REPLACE MASKING POLICY GP_PROBE2.S.MP AS (v STRING) RETURNS STRING -> '***'"],
      ["ROW ACCESS POLICY",  "CREATE OR REPLACE ROW ACCESS POLICY GP_PROBE2.S.RP AS (v STRING) RETURNS BOOLEAN -> TRUE"],
      ["TAG",                "CREATE OR REPLACE TAG GP_PROBE2.S.T1"],
    ];
    for (const [label, sql] of tests) {
      try { await q(sql); console.log("OK  ", label); }
      catch (e) { console.log("ERR ", label.padEnd(20), e.message.replace(/\s+/g," ").slice(0, 95)); }
    }
    // Retention ceiling tells us the edition indirectly: Standard caps at 1 day.
    try {
      await q("ALTER DATABASE GP_PROBE2 SET DATA_RETENTION_TIME_IN_DAYS = 90");
      const r = await q("SHOW PARAMETERS LIKE 'DATA_RETENTION_TIME_IN_DAYS' IN DATABASE GP_PROBE2");
      console.log("OK   retention 90 accepted ->", JSON.stringify(r[0]?.value));
    } catch (e) { console.log("ERR  retention 90        ", e.message.replace(/\s+/g," ").slice(0, 95)); }
  } finally {
    try { await q("DROP DATABASE IF EXISTS GP_PROBE2"); console.log("scratch dropped"); } catch {}
  }
  conn.destroy(() => process.exit(0));
});
