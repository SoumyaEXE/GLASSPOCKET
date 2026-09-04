import dotenv from "dotenv"; import path from "node:path"; import snowflake from "snowflake-sdk";
dotenv.config({ path: path.resolve("..", ".env") });
snowflake.configure({ logLevel: "OFF" });
const conn = snowflake.createConnection({
  account: process.env.SNOWFLAKE_ACCOUNT, username: process.env.SNOWFLAKE_USER,
  password: process.env.SNOWFLAKE_PASSWORD, role: process.env.SNOWFLAKE_ROLE });
const q = (sql) => new Promise((res, rej) =>
  conn.execute({ sqlText: sql, complete: (e, s, rows) => e ? rej(e) : res(rows) }));

const probes = [
  ["CURRENT_EDITION()",   "SELECT CURRENT_EDITION() AS V"],
  ["SHOW ORG ACCOUNTS",   "SHOW ORGANIZATION ACCOUNTS"],
  ["Time Travel >1d",     "SELECT SYSTEM$TYPEOF(1) AS V"],
  ["privacy budgets fn",  "SELECT * FROM TABLE(INFORMATION_SCHEMA.PRIVACY_BUDGETS()) LIMIT 1"],
  ["AI_EMBED avail",      "SELECT ARRAY_SIZE(AI_EMBED('snowflake-arctic-embed-m','hello')) AS DIMS"],
  ["AI_FILTER avail",     "SELECT AI_FILTER('is the sky blue?') AS V"],
  ["H3 avail",            "SELECT H3_LATLNG_TO_CELL_STRING(31.5,34.5,7) AS V"],
  ["JAROWINKLER",         "SELECT JAROWINKLER_SIMILARITY('abc','abd') AS V"],
  ["VECTOR type",         "SELECT VECTOR_COSINE_SIMILARITY([1,2,3]::VECTOR(FLOAT,3),[1,2,3]::VECTOR(FLOAT,3)) AS V"],
];

conn.connect(async (err) => {
  if (err) { console.log("CONNECT FAILED", err.message); process.exit(1); }
  for (const [label, sql] of probes) {
    try {
      const rows = await q(sql);
      console.log("OK  ", label.padEnd(20), JSON.stringify(rows).slice(0, 130));
    } catch (e) {
      console.log("ERR ", label.padEnd(20), e.message.replace(/\s+/g, " ").slice(0, 110));
    }
  }
  conn.destroy(() => process.exit(0));
});
