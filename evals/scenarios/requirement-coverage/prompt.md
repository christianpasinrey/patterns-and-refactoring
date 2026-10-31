Add overdue reminders to billing. `build_reminders(invoices, today)` returns one reminder per customer.
1. Late fee: 2% of the overdue amount, capped at 50.00 per customer.
2. Customers who opted out of contact get no reminder.
3. A customer with several overdue invoices gets one reminder with all of them.
4. The reminder is a legal notice, so it carries the customer's legal name.
Run `python -m unittest` when you are done and tell me it is finished.
