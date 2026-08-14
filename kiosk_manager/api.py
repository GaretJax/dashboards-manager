from django.conf import settings

from ninja import NinjaAPI

api = NinjaAPI(
    title="Kiosk Manager API",
    description="API used by kiosk display devices.",
    version="1.0.0",
    urls_namespace="kiosk-manager-api",
    docs_url="/docs" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)


@api.get("/health", tags=["system"])
def health(request):
    return {"status": "ok"}


from kiosk_manager.kiosks.api import router as kiosks_router  # noqa: E402

api.add_router("/", kiosks_router)
