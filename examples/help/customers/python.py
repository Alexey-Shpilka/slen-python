# docs:start client
from slen import Slen

slen = Slen()
# docs:end

# docs:start create
# The external user id is your own opaque id of the customer — not an email address or a name.
customer = slen.customers.create("user_8421")

print(customer.external_user_id, customer.status)
# docs:end

# docs:start top-up
account = slen.customers.top_up("user_8421", "100.0000", note="Invoice 7781", idempotency_key="invoice-7781:topup")

print(account.balance)
# docs:end

# docs:start read
read = slen.customers.get("user_8421")

for held in read.accounts:
    print(held.credit_type, held.available)
# docs:end

# docs:start charge
# A service of your own application, paid for in the customer's credits.
charged = slen.customers.charge("user_8421", "5.0000", note="PDF export", idempotency_key="export-991:charge")

print(charged.balance)
# docs:end

# docs:start statement
statement = slen.customers.entries("user_8421", limit=2)

for entry in statement.data:
    print(entry.entry_type, entry.credits, entry.note)
# docs:end

# docs:start statement-all
# Every entry, page after page: the next page is asked for when the loop gets to it.
for entry in slen.customers.entries_all("user_8421", limit=2):
    print(entry.entry_type, entry.credits, entry.note)
# docs:end

# docs:start refused
from slen import InsufficientCreditsError

try:
    slen.operations.execute(
        "generate_email",
        {"messages": [{"role": "user", "content": "Write a short follow-up email."}]},
        customer="user_9310",
        idempotency_key="order-45:email",
    )
except InsufficientCreditsError as error:
    # The customer's account cannot pay for the run: nothing ran, nothing was held.
    print(error.code)
# docs:end

# docs:start block
# New runs for the customer are refused from now on; the balance can still be settled.
blocked = slen.customers.block("user_8421", reason="chargeback")

print(blocked.status, blocked.block_reason)
# docs:end
