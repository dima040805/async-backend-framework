from aiohttp_apispec import docs, response_schema

from app.web.app import View
from app.web.schemes import OkResponseSchema
from app.web.utils import json_response


class AdminLoginView(View):
    @docs(tags=["admin"], summary="Admin login", description="Login as admin")
    @response_schema(OkResponseSchema, 200)
    async def post(self):
        return json_response(data={"message": "Admin login endpoint"})


class AdminCurrentView(View):
    @docs(
        tags=["admin"],
        summary="Get current admin",
        description="Get current admin info",
    )
    @response_schema(OkResponseSchema, 200)
    async def get(self):
        return json_response(data={"message": "Admin current endpoint"})
