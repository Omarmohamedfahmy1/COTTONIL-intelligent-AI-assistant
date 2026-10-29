"""Official SDK, fixed HTTPS origin, redacted errors and bounded retries only."""
import logging,ssl,time,math
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
import re
import httpx
from groq import Groq

class ProviderError(Exception):
    def __init__(self,code,retry_after=None):
        self.code=code;self.retry_after=retry_after
        super().__init__(code)

def groq_only(request):
    if request.url.scheme!='https' or request.url.host!='api.groq.com' or request.url.port not in (None,443) or request.url.userinfo:
        raise ProviderError('provider_policy')

class GroqProvider:
    def __init__(self,settings,client=None,max_requests=9):
        self.settings=settings
        self.requests=0
        self.max_requests=max_requests;self.rate_limit_errors=0;self.last_error_detail=None
        if not settings.api_key:raise ProviderError('missing_key')
        # SDK/HTTP debug bodies and headers must never enter application logs.
        for name in ('groq','httpx','httpcore'):logging.getLogger(name).setLevel(logging.CRITICAL)
        self.client=client or Groq(api_key=settings.api_key,base_url='https://api.groq.com',
            timeout=settings.timeout,max_retries=0,http_client=httpx.Client(verify=ssl.create_default_context(),
                timeout=settings.timeout,follow_redirects=False,event_hooks={'request':[groq_only]}))

    def _request(self,fn):
        for attempt in range(2):
            if self.requests>=self.max_requests:raise ProviderError('request_budget')
            self.requests+=1
            try:return fn()
            except ProviderError:raise
            except Exception as error:
                status=getattr(error,'status_code',None)
                body=getattr(error,'body',None)
                detail=body.get('error',body).get('code') if isinstance(body,dict) and isinstance(body.get('error',body),dict) else None
                self.last_error_detail=detail if isinstance(detail,str) and re.fullmatch('[a-z_]{1,60}',detail) else None
                if status==429:self.rate_limit_errors+=1
                code={400:'invalid_request',401:'authentication',403:'permission',404:'model_access',429:'rate_limit'}.get(status,
                    'upstream' if status and status>=500 else 'network')
                delay=1
                try:
                    header=error.response.headers.get('retry-after')
                    if header is not None:
                        try:
                            parsed=float(header)
                            delay=max(1,parsed) if math.isfinite(parsed) else 60
                        except (ValueError,TypeError):
                            try:delay=max(1,(parsedate_to_datetime(header)-datetime.now(timezone.utc)).total_seconds())
                            except (ValueError,TypeError,OverflowError):delay=60
                except AttributeError:pass
                if attempt==0 and (status==429 or (status and status>=500) or status is None) and delay<=3:
                    time.sleep(delay);continue
                raise ProviderError(code,delay if code=='rate_limit' else None) from None

    def models(self):
        return sorted(m.id for m in self._request(self.client.models.list).data)

    def complete(self,messages,tools,max_tokens=None):
        # Local functions only; never Groq built-in code/browser or remote MCP tools.
        return self._request(lambda:self.client.chat.completions.create(model=self.settings.model,messages=messages,
            tools=tools,tool_choice='auto',parallel_tool_calls=False,temperature=0,
            max_completion_tokens=max_tokens or self.settings.output_tokens))

    def close(self):self.client.close()
