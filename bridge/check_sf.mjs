import dotenv from "dotenv";
import path from "node:path";
import snowflake from "snowflake-sdk";
dotenv.config({ path: path.resolve("..", ".env") });
snowflake.configure({ logLevel: "OFF" });

const conn = snowflake.createConnection({
  account: process.env.SNOWFLAKE_ACCOUNT,
  username: process.env.SNOWFLAKE_USER,
  password: process.env.SNOWFLAKE_PASSWORD,
  role: process.env.SNOWFLAKE_ROLE,
});
const q = (sql) => new Promise((res, rej) =>
  conn.execute({ sqlText: sql, complete: (e, s, rows) => e ? rej(e) : res(rows) }));

conn.connect(async (err) => {
  if (err) { console.log("CONNECT FAILED:", err.message.split("\n")[0]); process.exit(1); }
  console.log("connected OK as account:", process.env.SNOWFLAKE_ACCOUNT);
  for (const [label, sql] of [
    ["account/region", "SELECT CURRENT_ACCOUNT() AS A, CURRENT_REGION() AS R"],
    ["EDITION       ", "SELECT CURRENT_EDITION() AS EDITION"],
    ["user/role     ", "SELECT CURRENT_USER() AS U, CURRENT_ROLE() AS RL"],
    ["warehouses    ", "SHOW WAREHOUSES"],
  ]) {
    try {
      const rows = await q(sql);
      console.log(label, JSON.stringify(rows).slice(0, 200));
    } catch (e) { console.log(label, "ERR", e.message.split("\n")[0].slice(0, 90)); }
  }
  conn.destroy(() => process.exit(0));
});
