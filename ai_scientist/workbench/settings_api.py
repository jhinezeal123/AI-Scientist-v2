"""Settings endpoints. Secret inputs are never echoed in validation responses."""
import json
from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, SecretStr, ValidationError

from .models import StrictModel
from .store import StoreConflict


class AccountInput(StrictModel):
    username: str = Field(min_length=1, max_length=64, pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]*$')
    token: SecretStr
    password: SecretStr


def settings_router():
    router = APIRouter(prefix='/api/settings/kaggle-proxy')

    async def call(operation, *args):
        try:
            return await operation(*args)
        except (StoreConflict, RuntimeError) as exc:
            raise HTTPException(409, str(exc)) from None
        except (ValueError, KeyError):
            raise HTTPException(422, 'Account hoặc cấu hình không hợp lệ') from None

    def same_origin(request):
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            raise HTTPException(403, 'Chỉ thực hiện thao tác từ Workbench này')

    @router.get('')
    async def snapshot(request: Request, refresh: bool = False):
        return await call(request.app.state.kaggle_settings.snapshot, refresh)

    @router.post('/accounts', status_code=202)
    async def add(request: Request):
        same_origin(request)
        body = await request.body()
        try:
            if len(body) > 8000:
                raise ValueError()
            parsed = AccountInput.model_validate(json.loads(body))
            token, password = parsed.token.get_secret_value(), parsed.password.get_secret_value()
            if not 1 <= len(password) <= 512 or not 1 <= len(token) <= 1100:
                raise ValueError()
        except (ValueError, ValidationError):
            raise HTTPException(422, 'Cần tên tài khoản Kaggle, token KGAT và mật khẩu hợp lệ') from None
        return await call(request.app.state.kaggle_settings.add,
                          {'username': parsed.username, 'token': token, 'password': password})

    @router.delete('/accounts/{account}')
    async def remove(account: str, request: Request):
        same_origin(request)
        return await call(request.app.state.kaggle_settings.remove, account)

    @router.post('/check-cookie', status_code=202)
    async def check(request: Request):
        same_origin(request)
        try:
            service = request.app.state.kaggle_settings
            if service.mutation_lock.locked():
                raise StoreConflict('Chờ thao tác account hoàn tất trước khi check cookie')
            return service.start_cookie_check()
        except (ValueError, StoreConflict) as exc:
            raise HTTPException(409, str(exc)) from None

    return router
