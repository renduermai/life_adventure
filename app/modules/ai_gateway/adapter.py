"""Provider protocol boundary, independent of persistence and business modules."""
import json
import logging
import os
from pydantic import ValidationError
from app.modules.ai_gateway.security import AIError


class OpenAICompatibleAdapter:
    def __init__(self, transport):
        self.transport=transport

    def generate(self,url,key,model,messages,output_schema=None,max_tokens=512,json_mode=False,*,enable_thinking=None,diagnostics=False):
        payload={'model':model,'messages':messages,'max_tokens':max_tokens}
        if output_schema:
            payload['messages']=[{'role':'system','content':'Return only a JSON object matching this schema: '+json.dumps(output_schema.model_json_schema())}]+messages
        if json_mode:payload['response_format']={'type':'json_object'}
        if enable_thinking is not None:payload['enable_thinking']=enable_thinking
        stage='request';raw=None;content=None
        try:
            raw=self.transport(url,key,payload)
            stage='extract'
            reported=raw.get('usage') if isinstance(raw,dict) else None
            usage={k:v for k,v in reported.items() if k in {'prompt_tokens','completion_tokens','total_tokens'} and type(v) is int and 0<=v<=1000000000} if isinstance(reported,dict) else {}
            if diagnostics:
                choice=raw.get('choices',[{}])[0] if isinstance(raw,dict) and isinstance(raw.get('choices'),list) and raw['choices'] else {}
                choice=choice if isinstance(choice,dict) else {}
                msg=choice.get('message') if isinstance(choice.get('message'),dict) else {}
                reason=choice.get('finish_reason')
                details=reported.get('completion_tokens_details') if isinstance(reported,dict) else None
                reasoning_tokens=details.get('reasoning_tokens') if isinstance(details,dict) else None
                if type(reasoning_tokens) is int and 0<=reasoning_tokens<=1000000000:usage['reasoning_tokens']=reasoning_tokens
                usage.update(output_budget=max_tokens,finish_reason=reason if reason in ('stop','length','tool_calls','content_filter') else 'unknown',
                    content_length=len(msg['content']) if isinstance(msg.get('content'),str) else None,
                    reasoning_length=len(msg['reasoning_content']) if isinstance(msg.get('reasoning_content'),str) else None,
                    thinking_enabled=enable_thinking)
                logging.getLogger('adventure_camp').info('person_analysis_output_metrics %s',json.dumps(usage,sort_keys=True))
            if raw['choices'][0].get('finish_reason')=='length':
                error=AIError('output_truncated','模型输出达到长度限制，任务尚未完成分析',502)
                if diagnostics:error.usage=usage
                raise error
            content=raw['choices'][0]['message']['content']
            if not isinstance(content,str) or len(content)>32000:
                raise ValueError()
            if output_schema:
                stage='validate_json_schema'
                content=output_schema.model_validate_json(content)
            return content,usage or None
        except AIError:
            raise
        except Exception as exc:
            if os.getenv('ADVENTURE_AI_DIAG')=='1':
                choice=raw.get('choices',[None])[0] if isinstance(raw,dict) and isinstance(raw.get('choices'),list) and raw['choices'] else None
                msg=choice.get('message') if isinstance(choice,dict) else None
                parsed=None
                if isinstance(content,str) and len(content)<=32000:
                    try:parsed=json.loads(content)
                    except ValueError:pass
                errors=[] if isinstance(exc,ValidationError) else None
                if errors is not None:
                    for item in exc.errors(include_input=False,include_url=False):
                        node=parsed
                        for part in item['loc']:
                            node=node.get(part) if isinstance(node,dict) else node[part] if isinstance(node,list) and isinstance(part,int) and 0<=part<len(node) else None
                        safe_loc=[part if isinstance(part,int) or part in {'reply','steps','title','detail','minutes','done_when','minimum_index','state_advice','ready','pressure','energy','difficulty','barrier','goal'} else '<extra>' for part in item['loc']]
                        errors.append({'loc':safe_loc,'type':item['type'],'actual_type':type(node).__name__ if node is not None else 'missing_or_null'})
                logging.getLogger('adventure_camp').error('ai_parse_diagnostic stage=%s exception=%s root_type=%s root_keys=%s choice_type=%s finish_reason=%s message_keys=%s content_type=%s content_len=%s errors=%s',stage,type(exc).__name__,type(raw).__name__,sorted(raw.keys()) if isinstance(raw,dict) else None,type(choice).__name__,choice.get('finish_reason') if isinstance(choice,dict) else None,sorted(msg.keys()) if isinstance(msg,dict) else None,type(content).__name__,len(content) if isinstance(content,str) else None,errors)
            code='invalid_json' if isinstance(exc,ValidationError) and any(e['type']=='json_invalid' for e in exc.errors(include_input=False,include_url=False)) else 'invalid_schema' if isinstance(exc,ValidationError) else 'invalid_output'
            raise AIError(code,'模型输出不符合要求，结果未保存到正式业务',502) from None
