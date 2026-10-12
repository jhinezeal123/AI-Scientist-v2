"""Proposal discussion: only a human message authorizes another planning turn."""
import asyncio
import time


class ProposalDiscussion:
    def __init__(self, owner):
        self.owner = owner

    async def decision(self, runtime, candidate, approval_schema):
        needs_answer = candidate['body']['needs_clarification']
        if not needs_answer and runtime.spec.stages['approval'].actor == 'agent':
            return await asyncio.to_thread(runtime.invoke, 'approval',
                {'goal':runtime.spec.goal,'proposal':candidate,'operator_grant':runtime.spec.model_dump(),
                 'instruction':'Approve only if this proposal implements the goal, uses the pinned benchmark/context and stays inside the operator grant. Return approve=false with a reason otherwise.'},
                approval_schema, timeout=86400)
        message_schema = {'type':'object','required':['message','request_id'],'properties':{
            'message':{'type':'string','minLength':1,'maxLength':20000,'pattern':r'\S'},
            'request_id':{'type':'string','pattern':'^[a-f0-9]{32}$'}},'additionalProperties':False}
        schema = {'oneOf':[message_schema] + ([] if needs_answer else [approval_schema])}
        prompt = {'kind':'proposal','candidate':candidate,'approval_allowed':not needs_answer,
                  'questions':candidate['body'].get('questions',[]),'schema':schema,
                  'proposal_round':self.owner.store.get(runtime.project,runtime.workflow)['state'].get('proposal_round',0)}
        result = await asyncio.to_thread(runtime.human,'approval',prompt,time.monotonic()+86400,lambda:False)
        if 'message' in result:
            runtime.check()
            self.owner.store.revise_proposal(runtime.project,runtime.workflow,candidate,result['message'],result['request_id'])
            return {'revise_proposal':True}
        return result
