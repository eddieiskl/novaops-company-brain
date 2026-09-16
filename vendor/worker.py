"""Single-worker SQS adapter; persistent SQLite cache, at-least-once results.

Mount the cache persistently. Result consumers deduplicate by source_id because
publication followed by an acknowledgement is not an atomic transaction.
"""
import hashlib
import json
import os
import sqlite3
from vendor.runtime import extract_request

class VendorQueueConsumer:
    def __init__(self, sqs, input_url, result_url, cache_path, extract=None):
        self.sqs, self.input_url, self.result_url = sqs, input_url, result_url
        self.extract = extract or extract_request
        self.db = sqlite3.connect(cache_path)
        self.db.execute('CREATE TABLE IF NOT EXISTS results (source_id TEXT PRIMARY KEY, digest TEXT NOT NULL, body TEXT NOT NULL)')
        self.db.commit()

    def process(self, message):
        from service.api import VendorExtractionRequest
        request = VendorExtractionRequest.model_validate_json(message['Body'])
        digest = hashlib.sha256(json.dumps(request.model_dump(), sort_keys=True).encode()).hexdigest()
        row = self.db.execute('SELECT digest, body FROM results WHERE source_id=?', (request.source_id,)).fetchone()
        if row:
            if row[0] != digest:
                raise ValueError('source_id already used for different input')
            body = row[1]
        else:
            result = self.extract(request.source_id, request.source_type, request.document)
            body = json.dumps({'source_id': request.source_id, 'status': 'completed', 'result': result.as_dict()})
            self.db.execute('INSERT INTO results VALUES (?, ?, ?)', (request.source_id, digest, body))
            self.db.commit()
        self.sqs.send_message(QueueUrl=self.result_url, MessageBody=body)
        self.sqs.delete_message(QueueUrl=self.input_url, ReceiptHandle=message['ReceiptHandle'])

    def run_once(self):
        messages = self.sqs.receive_message(QueueUrl=self.input_url, MaxNumberOfMessages=1,
                                            WaitTimeSeconds=20, VisibilityTimeout=300).get('Messages', [])
        for message in messages:
            self.process(message)
        return len(messages)

def main():
    import boto3
    worker = VendorQueueConsumer(boto3.client('sqs'), os.environ['VENDOR_INPUT_QUEUE_URL'],
                                os.environ['VENDOR_RESULT_QUEUE_URL'],
                                os.environ.get('VENDOR_CACHE_PATH', 'vendor-results.sqlite3'))
    while True:
        try:
            worker.run_once()
        except Exception as error:
            print(f'vendor message retained: {type(error).__name__}', flush=True)

if __name__ == '__main__':
    main()
