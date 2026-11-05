"""Entry point: `python run.py`. Binds to localhost by default (see
app/config.py) since this app holds personal documents."""
import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
