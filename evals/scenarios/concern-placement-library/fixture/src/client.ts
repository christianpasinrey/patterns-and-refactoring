export type ClientOptions = { apiKey: string; baseUrl?: string };
export type Invoice = { id: string; total: number };

export class InvoicesClient {
  private readonly baseUrl: string;

  constructor(private readonly options: ClientOptions) {
    this.baseUrl = options.baseUrl ?? "https://api.acme.example";
  }

  async getInvoice(id: string): Promise<Invoice> {
    const response = await fetch(`${this.baseUrl}/invoices/${id}`, {
      headers: { Authorization: `Bearer ${this.options.apiKey}` },
    });
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`);
    }
    return (await response.json()) as Invoice;
  }
}
