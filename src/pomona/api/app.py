from fastapi import FastAPI

from pomona.api import clinical_records, ecg, meta, metrics, overview, pages, workouts

app = FastAPI(title="Pomona")
for module in (meta, overview, metrics, workouts, ecg, clinical_records):
    app.include_router(module.router)
pages.mount_frontend(app)
