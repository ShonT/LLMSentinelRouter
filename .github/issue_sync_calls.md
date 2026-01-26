Transitioning to Asynchronous I/O (async/await)

In a synchronous gateway, every request occupies a worker thread. If Anthropic takes 30 seconds to stream a response, that thread is "dead" to the rest of the system. At high RPS (Requests Per Second), you will quickly exhaust your thread pool.

The Implementation: httpx.AsyncClient

You should move to a singleton AsyncClient pattern. This allows for connection pooling, which is significantly more efficient than opening a new connection for every request.

Refactored clients.py logic:

Python
import httpx

class AsyncLLMClient:
    def __init__(self):
        # Connection pooling: keep 100 connections open, max 20 idle
        self.client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            timeout=httpx.Timeout(60.0)
        )

    async def call_provider(self, model: str, messages: list):
        # Non-blocking I/O
        response = await self.client.post(
            f"{BASE_URL}/chat/completions",
            json={"model": model, "messages": messages},
            headers={"Authorization": f"Bearer {API_KEY}"}
        )
        response.raise_for_status()
        return response.json()
Why this works: The event loop can now pause execution of the "Claude" task while waiting for the network socket, allowing the "Judge" task to run in the interim.