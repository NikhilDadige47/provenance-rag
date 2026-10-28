with open('src/retrieval/embed.py', 'rb') as f:
    content = f.read()

old = (
    b'        self._http_client = SecureHttpClient.create_async_client()\r\n'
    b'        # Circuit breaker state\r\n'
    b'        self._failure_count: int = 0\r\n'
    b'        self._circuit_open_until: float = 0.0\r\n'
)
new = (
    b'        # Lazy-initialized: avoids creating an httpx event-loop connection pool\r\n'
    b'        # at import / construction time, which hangs in sandboxed environments.\r\n'
    b'        self._http_client = None\r\n'
    b'        # Circuit breaker state\r\n'
    b'        self._failure_count: int = 0\r\n'
    b'        self._circuit_open_until: float = 0.0\r\n'
    b'\r\n'
    b'    def _get_http_client(self):\r\n'
    b'        """Return the shared async HTTP client, creating it on first use."""\r\n'
    b'        if self._http_client is None:\r\n'
    b'            self._http_client = SecureHttpClient.create_async_client()\r\n'
    b'        return self._http_client\r\n'
)

if old in content:
    content = content.replace(old, new, 1)
    with open('src/retrieval/embed.py', 'wb') as f:
        f.write(content)
    print('PATCHED embed.py OK')
else:
    print('PATTERN NOT FOUND')

