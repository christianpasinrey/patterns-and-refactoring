import { createHmac } from "node:crypto";
import { dueEndpoints, recordFailure } from "../webhooks/store.js";

// Runs forever. Customers verify the signature, so a bad one counts as a failed delivery,
// and three failures pause the endpoint until the customer turns it back on.
async function tick(): Promise<void> {
  for (const endpoint of await dueEndpoints()) {
    const body = JSON.stringify({ type: "ping" });
    const signature = createHmac("sha256", endpoint.signing_secret).update(body).digest("hex");
    const response = await fetch(endpoint.url, {
      method: "POST",
      headers: { "X-Signature": signature },
      body,
    });
    if (!response.ok) {
      await recordFailure(endpoint.id);
    }
  }
}

setInterval(() => void tick(), 60_000);
