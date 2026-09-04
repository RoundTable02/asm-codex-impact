from httpx import ASGITransport, AsyncClient

from app.main import create_app


async def test_health_endpoints_are_available(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("AI_MODE", "fake")
    app = create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/health/live")).json() == {"status": "ok"}
            assert (await client.get("/health/ready")).json() == {"status": "ready"}
