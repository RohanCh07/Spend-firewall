# Mock provider

A fake OpenAI-compatible endpoint for demos and load tests. Point the gateway at it with
`UPSTREAM_OVERRIDE_BASE_URL=http://localhost:9000/v1` and use model `mock-model`.

```bash
pip install fastapi uvicorn
uvicorn server:app --port 9000
```
