from fastapi import FastAPI

from pomona.api import dashboard, pages

app = FastAPI(title="Pomona")
app.include_router(dashboard.router)
pages.mount_frontend(app)
