from fastapi import APIRouter

from cottage_monitoring.api.commands import router as commands_router
from cottage_monitoring.api.devices import router as devices_router
from cottage_monitoring.api.events import router as events_router
from cottage_monitoring.api.houses import router as houses_router
from cottage_monitoring.api.objects import router as objects_router
from cottage_monitoring.api.rpc import router as rpc_router
from cottage_monitoring.api.schemas import router as schemas_router
from cottage_monitoring.api.state import router as state_router

api_router = APIRouter()

api_router.include_router(houses_router, tags=["houses"])
api_router.include_router(devices_router, tags=["devices"])
api_router.include_router(state_router, tags=["state"])
api_router.include_router(events_router, tags=["events"])
api_router.include_router(objects_router, tags=["objects"])
api_router.include_router(commands_router, tags=["commands"])
api_router.include_router(schemas_router, tags=["schemas"])
api_router.include_router(rpc_router, tags=["rpc"])
