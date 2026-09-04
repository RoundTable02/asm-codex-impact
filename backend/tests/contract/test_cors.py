from httpx import ASGITransport, AsyncClient

from app.main import create_app


async def test_hackathon_default_allows_cross_origin_requests(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("AI_MODE", "fake")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.options(
                "/health/live",
                headers={
                    "Origin": "https://frontend-hackathon.example",
                    "Access-Control-Request-Method": "GET",
                },
            )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
