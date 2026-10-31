import pg from "pg";

export const pool = new pg.Pool();

export type Endpoint = { id: number; url: string; signing_secret: string; failures: number };

export async function dueEndpoints(): Promise<Endpoint[]> {
  const { rows } = await pool.query("SELECT * FROM webhook_endpoints WHERE paused = false");
  return rows;
}

export async function createEndpoint(url: string, signingSecret: string): Promise<void> {
  await pool.query("INSERT INTO webhook_endpoints (url, signing_secret) VALUES ($1, $2)", [url, signingSecret]);
}

export async function recordFailure(id: number): Promise<void> {
  await pool.query(
    "UPDATE webhook_endpoints SET failures = failures + 1, paused = failures + 1 >= 3 WHERE id = $1",
    [id],
  );
}
