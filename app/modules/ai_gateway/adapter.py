"""Provider protocol boundary, independent of persistence and business modules."""
import json
from app.modules.ai_gateway.security import AIError


class OpenAICompatibleAdapter:
    def __init__(self, transport):
        self.transport=transport

    def generate(self,url,key,model,messages,output_schema=None,max_tokens=512):
        payload={'model':model,'messages':messages,'max_tokens':max_tokens}
        if output_schema:
            payload['messages']=[{'role':'system','content':'Return only a JSON object matching this schema: '+json.dumps(output_schema.model_json_schema())}]+messages
        try:
            raw=self.transport(url,key,payload)
            content=raw['choices'][0]['message']['content']
            if not isinstance(content,str) or len(content)>32000:
                raise ValueError()
            if output_schema:
                content=output_schema.model_validate_json(content)
            reported=raw.get('usage')
            usage=None
            if isinstance(reported,dict):
                usage={k:v for k,v in reported.items() if k in {'prompt_tokens','completion_tokens','total_tokens'} and type(v) is int and 0<=v<=1000000000} or None
            return content,usage
        except AIError:
            raise
        except Exception:
            raise AIError('invalid_output','模型输出不符合要求，结果未保存到正式业务',502) from None
