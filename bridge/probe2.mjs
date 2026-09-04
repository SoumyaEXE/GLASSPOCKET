import dotenv from "dotenv"; import path from "node:path"; import snowflake from "snowflake-sdk";
dotenv.config({ path: path.resolve("..", ".env") });
snowflake.configure({ logLevel: "OFF" });
const conn = snowflake.createConnection({
  account: process.env.SNOWFLAKE_ACCOUNT, username: process.env.SNOWFLAKE_USER,
  password: process.env.SNOWFLAKE_PASSWORD, role: process.env.SNOWFLAKE_ROLE });
const q = (sql) => new Promise((res, rej) =>
  conn.execute({ sqlText: sql, complete: (e, s, rows) => e ? rej(e) : res(rows) }));

const probes = [
  ["cortex EMBED_768",  "SELECT ARRAY_SIZE(SNOWFLAKE.CORTEX.EMBED_TEXT_768('snowflake-arctic-embed-m','hello')::ARRAY) AS DIMS"],
  ["cortex EMBED_1024", "SELECT ARRAY_SIZE(SNOWFLAKE.CORTEX.EMBED_TEXT_1024('snowflake-arctic-embed-l-v2.0','hello')::ARRAY) AS DIMS"],
  ["cortex COMPLETE",   "SELECT SNOWFLAKE.CORTEX.COMPLETE('mistral-7b','say ok') AS V"],
  ["cortex SENTIMENT",  "SELECT SNOWFLAKE.CORTEX.SENTIMENT('great') AS V"],
  ["semantic view DDL", "SHOW SEMANTIC VIEWS"],
  ["dynamic table DDL", "SHOW DYNAMIC TABLES"],
];
conn.connect(async (err) => {
  if (err) { console.log("CONNECT FAILED", err.message); process.exit(1); }
  for (const [label, sql] of probes) {
    try { console.log("OK  ", label.padEnd(18), JSON.stringify(await q(sql)).slice(0, 110)); }
    catch (e) { console.log("ERR ", label.padEnd(18), e.message.replace(/\s+/g," ").slice(0, 105)); }
  }

  // Trap 01, the unrecoverable one. Fully reversible probe: create a
  // scratch database, attempt the differential privacy DDL, drop it.
  console.log("\n--- differential privacy probe (scratch db, dropped after) ---");
  try {
    await q("CREATE DATABASE IF NOT EXISTS GP_EDITION_PROBE");
    await q("CREATE SCHEMA IF NOT EXISTS GP_EDITION_PROBE.S");
    try {
      await q("CREATE OR REPLACE PRIVACY BUDGET GP_EDITION_PROBE.S.PB TYPE = per_query_epsilon EPSILON = 0.1 REFRESH_PERIOD = 24");
      console.log("OK   CREATE PRIVACY BUDGET");
    } catch (e) { console.log("ERR  CREATE PRIVACY BUDGET  ", e.message.replace(/\s+/g," ").slice(0, 100)); }
    try {
      await q("CREATE OR REPLACE PRIVACY POLICY GP_EDITION_PROBE.S.PP AS () RETURNS privacy_budget -> CASE WHEN CURRENT_ROLE()='ACCOUNTADMIN' THEN no_privacy_policy() ELSE privacy_budget(name => 'default') END");
      console.log("OK   CREATE PRIVACY POLICY");
    } catch (e) { console.log("ERR  CREATE PRIVACY POLICY  ", e.message.replace(/\s+/g," ").slice(0, 100)); }
    try {
      await q("CREATE OR REPLACE TABLE GP_EDITION_PROBE.S.T (id STRING, amt NUMBER)");
      await q("CREATE OR REPLACE VIEW GP_EDITION_PROBE.S.V AS SELECT * FROM GP_EDITION_PROBE.S.T");
      await q("ALTER VIEW GP_EDITION_PROBE.S.V SET PRIVACY POLICY GP_EDITION_PROBE.S.PP ENTITY KEY (id)");
      console.log("OK   ATTACH POLICY WITH ENTITY KEY");
    } catch (e) { console.log("ERR  ATTACH POLICY          ", e.message.replace(/\s+/g," ").slice(0, 100)); }
  } finally {
    try { await q("DROP DATABASE IF EXISTS GP_EDITION_PROBE"); console.log("scratch database dropped"); }
    catch (e) { console.log("CLEANUP FAILED, drop GP_EDITION_PROBE manually:", e.message.slice(0,80)); }
  }
  conn.destroy(() => process.exit(0));
});
