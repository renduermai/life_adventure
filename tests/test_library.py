from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.modules.library.schemas import Create, Update


@pytest.mark.parametrize('url', ['http:example.com','https:/example.com','javascript:alert(1)','ftp://example.com/a','https://u:p@example.com','https://example.com/ a','https://example.com/\nfoo','https://','/relative','https://example.com\\evil','https://example.com/'+ 'x'*2048])
def test_invalid_urls(url):
    with pytest.raises(ValidationError): Create(request_id=uuid4(),description='描述',url=url,task_id=uuid4())


def test_exact_original_and_exclusive_target():
    url='https://example.com/a?x=1&b=2#part'
    value=Create(request_id=uuid4(),description='  原始描述  ',url=url,task_id=uuid4())
    assert value.url==url and value.description=='  原始描述  '
    for fields in ({},{'task_id':uuid4(),'main_quest_id':uuid4()}):
        with pytest.raises(ValidationError): Update(expected_version=1,**fields)
    with pytest.raises(ValidationError): Update(expected_version=True,task_id=uuid4())
