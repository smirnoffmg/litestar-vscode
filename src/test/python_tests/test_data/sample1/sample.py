from litestar import Controller, Litestar, get, post
from litestar.di import Provide


def get_db(): ...


@get("/health")
async def health_check() -> dict:
    return {"ok": True}


@get("/no-return-type")
async def missing_return(): ...


@post("/sync-handler")
def sync_handler(data: dict) -> dict: ...


class ItemController(Controller):
    path = "/items"

    @get()
    async def list_items(self) -> list[dict]: ...

    @post()
    async def create_item(self, data: dict) -> dict: ...


app = Litestar(
    route_handlers=[ItemController, health_check],
    dependencies={"db": Provide(get_db)},
)
