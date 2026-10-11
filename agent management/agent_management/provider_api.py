"""Human administrative endpoints for ACP Registry and provider setup."""
import hashlib
from typing import Annotated,Literal
from fastapi import APIRouter, Request
from pydantic import Field

from .api_support import authenticate,gateway
from .models import HarnessSpec,StrictModel


class InstallAction(StrictModel):
    operationId:str=Field(min_length=1,max_length=128)

class AuthStart(StrictModel):
    methodId:str=Field(default='',max_length=128)

class AuthFlow(StrictModel):
    flowId:str=Field(min_length=1,max_length=128)

class AuthCallback(AuthFlow):
    callbackUrl:str=Field(min_length=1,max_length=16384)

class AuthResponse(AuthFlow):
    interactionId:str=Field(min_length=1,max_length=128)
    response:Annotated['BrowserResponse | CredentialResponse | TerminalResponse',Field(discriminator='type')]

class BrowserResponse(StrictModel):
    type:Literal['browser']
    action:Literal['accept','decline']

class CredentialResponse(StrictModel):
    type:Literal['credentials']
    values:dict[str,str]=Field(max_length=16)

class TerminalSize(StrictModel):
    rows:int=Field(ge=2,le=150)
    cols:int=Field(ge=10,le=300)

class TerminalResponse(StrictModel):
    type:Literal['terminal']
    data:str=Field(max_length=4096)
    size:TerminalSize | None=None

AuthResponse.model_rebuild()


def create_provider_router(route_class):
    router=APIRouter(tags=['Provider setup'],route_class=route_class)
    def service(request): return gateway(request).harness_catalog.provider_setup
    def owner(request): return authenticate(request,'admin',human=True).id

    @router.get('/acp-registry')
    def search(request:Request,query:str='',refresh:bool=False):
        owner(request)
        if len(query)>256: raise ValueError('Registry search is too long')
        return service(request).registry.search(query,refresh)

    def temporary(identifier,request):
        agent=service(request).registry.agent(identifier)
        return HarnessSpec(id='prepare-'+hashlib.sha256(identifier.encode()).hexdigest()[:16],kind='acp',registry_agent_id=agent['id'])

    @router.post('/acp-registry/{identifier}/prepare')
    def prepare(identifier:str,request:Request):
        return service(request).start_install(temporary(identifier,request),owner(request))

    @router.get('/acp-registry/{identifier}/installation')
    def preparation(identifier:str,request:Request):
        owner(request)
        return service(request).install_state(temporary(identifier,request))

    @router.post('/acp-registry/{identifier}/installation/cancel')
    def cancel_preparation(identifier:str,body:InstallAction,request:Request):
        return service(request).cancel_install(temporary(identifier,request),owner(request),body.operationId)

    @router.get('/harnesses/{identifier}/installation')
    def installation(identifier:str,request:Request):
        owner(request)
        setup=service(request)
        return setup.install_state(setup.spec(identifier))

    @router.post('/harnesses/{identifier}/install')
    def install(identifier:str,request:Request):
        who=owner(request);setup=service(request)
        return setup.start_install(setup.spec(identifier),who)

    @router.post('/harnesses/{identifier}/installation/cancel')
    def cancel_install(identifier:str,body:InstallAction,request:Request):
        who=owner(request);setup=service(request)
        return setup.cancel_install(setup.spec(identifier),who,body.operationId)

    @router.delete('/harnesses/{identifier}/installation')
    def remove(identifier:str,request:Request):
        owner(request);setup=service(request)
        return setup.remove_installation(setup.spec(identifier))

    @router.get('/harnesses/{identifier}/auth')
    def auth(identifier:str,request:Request):
        who=owner(request);setup=service(request)
        return setup.auth_state(setup.spec(identifier),who)

    @router.post('/harnesses/{identifier}/auth/start')
    def start(identifier:str,body:AuthStart,request:Request):
        who=owner(request);setup=service(request)
        return setup.start_auth(setup.spec(identifier),who,body.methodId)

    @router.post('/harnesses/{identifier}/auth/respond')
    def respond(identifier:str,body:AuthResponse,request:Request):
        who=owner(request);setup=service(request)
        if len(str(body.response.model_dump()))>32768: raise ValueError('Sign-in response exceeds its limit')
        return setup.respond(setup.spec(identifier),who,body.model_dump())

    @router.post('/harnesses/{identifier}/auth/complete')
    def complete(identifier:str,body:AuthCallback,request:Request):
        who=owner(request);setup=service(request)
        return setup.complete_auth(setup.spec(identifier),who,body.model_dump())

    @router.post('/harnesses/{identifier}/auth/cancel')
    def cancel(identifier:str,body:AuthFlow,request:Request):
        who=owner(request);setup=service(request)
        return setup.cancel_auth(setup.spec(identifier),who,body.flowId)

    @router.post('/harnesses/{identifier}/auth/logout')
    def logout(identifier:str,request:Request):
        who=owner(request);setup=service(request)
        return setup.logout(setup.spec(identifier),who)

    return router
