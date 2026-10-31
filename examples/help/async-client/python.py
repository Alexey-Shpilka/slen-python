# docs:start client
import asyncio

from slen import AsyncSlen, ExecutionResult


async def main() -> None:
    # No api_key: the client reads SLEN_API_KEY. Leaving the block closes the client and its connections.
    async with AsyncSlen() as slen:
        runs = await send(slen)

    report(runs)
# docs:end


# docs:start send
async def send(slen: AsyncSlen) -> list[ExecutionResult]:
    # Two runs at once, each under the key of its own order.
    runs = await asyncio.gather(
        slen.operations.execute(
            "generate_email",
            {"messages": [{"role": "user", "content": "Write a short follow-up email to Ada."}]},
            idempotency_key="order-42:email",
        ),
        slen.operations.execute(
            "generate_email",
            {"messages": [{"role": "user", "content": "Write a short follow-up email to Grace."}]},
            idempotency_key="order-43:email",
        ),
    )

    return list(runs)
# docs:end


# docs:start result
def report(runs: list[ExecutionResult]) -> None:
    for run in runs:
        if run.is_completed():
            print(run.execution_id, run.status)


asyncio.run(main())
# docs:end
