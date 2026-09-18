import json
import pytest
from botocore.exceptions import ClientError
from vendor.extractor import VendorExtractor
from vendor.reliability import VendorSchemaError, call_with_retry, should_retry
from vendor.runtime import DeterministicVendorModel
from vendor.worker import VendorQueueConsumer

def error(code):
    return ClientError({'Error': {'Code': code, 'Message': 'test'}}, 'Converse')

@pytest.mark.parametrize('code,expected', [('ThrottlingException', True), ('ServiceUnavailableException', True), ('AccessDeniedException', False), ('ValidationException', False)])
def test_classifier(code, expected):
    assert should_retry(error(code)) is expected

def test_retry_budget_preserves_original_exception():
    original = error('ThrottlingException')
    calls, delays = [], []
    def fail():
        calls.append(1)
        raise original
    with pytest.raises(ClientError) as caught:
        call_with_retry(fail, sleep=delays.append, jitter=lambda lo, hi: hi)
    assert caught.value is original
    assert len(calls) == 3 and delays == [0.25, 0.5]
    assert not should_retry(RuntimeError('gateway failure'))

@pytest.mark.parametrize('recover', [True, False])
def test_exactly_one_repair(recover):
    class Model(DeterministicVendorModel):
        calls = 0
        def extract_with_tool(self, prompt, **kwargs):
            self.calls += 1
            if self.calls == 1 or not recover:
                return {'record': []}
            return super().extract_with_tool(prompt, **kwargs)
    model = Model()
    extractor = VendorExtractor(model)
    if recover:
        assert extractor.extract('a', 'formal_document', 'HelioDesk').missing_required_fields == []
    else:
        with pytest.raises(VendorSchemaError):
            extractor.extract('a', 'formal_document', 'HelioDesk')
    assert model.calls == 2

class Queue:
    def __init__(self):
        self.events = []
        self.fail = True
    def send_message(self, **kwargs):
        self.events.append('publish')
        if self.fail:
            raise RuntimeError('unavailable')
    def delete_message(self, **kwargs):
        self.events.append('delete')

def test_queue_publish_before_ack_and_durable_cache(tmp_path):
    calls = []
    def extract(*args):
        calls.append(1)
        return VendorExtractor(DeterministicVendorModel()).extract(*args)
    queue = Queue()
    path = tmp_path / 'cache.sqlite'
    msg = {'Body': json.dumps({'source_id': 'a', 'source_type': 'formal_document', 'document': 'HelioDesk'}), 'ReceiptHandle': 'handle'}
    worker = VendorQueueConsumer(queue, 'in', 'out', path, extract)
    with pytest.raises(RuntimeError):
        worker.process(msg)
    assert queue.events == ['publish']
    worker.db.close()
    queue.fail = False
    worker = VendorQueueConsumer(queue, 'in', 'out', path, extract)
    worker.process(msg)
    assert calls == [1] and queue.events == ['publish', 'publish', 'delete']
    msg['Body'] = msg['Body'].replace('HelioDesk', 'RoutePilot')
    with pytest.raises(ValueError, match='different input'):
        worker.process(msg)

def test_http_and_queue_share_extraction_function():
    from service import api
    from vendor import runtime, worker
    assert api.extract_request is runtime.extract_request is worker.extract_request


def test_http_reports_exhausted_model_repair_as_upstream_failure(monkeypatch):
    from fastapi.testclient import TestClient
    from service import api
    def fail(*args):
        raise VendorSchemaError('sensitive invalid model output')
    monkeypatch.setattr(api, 'extract_request', fail)
    response = TestClient(api.app).post('/v1/vendor/extract', json={
        'source_id': 'a', 'source_type': 'formal_document', 'document': 'HelioDesk'})
    assert response.status_code == 502
    assert response.json()['detail'] == 'model_output_invalid_after_repair'
