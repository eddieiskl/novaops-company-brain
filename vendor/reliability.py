"""One bounded transport retry budget, separate from schema repair."""
import random
import time


def should_retry(error: Exception) -> bool:
    # Lazy import keeps the gateway-only image independent of the AWS SDK.
    try:
        from botocore.exceptions import ClientError
    except ImportError:
        return False
    if not isinstance(error, ClientError):
        return False
    code = error.response.get('Error', {}).get('Code')
    return code in {'ThrottlingException', 'TooManyRequestsException',
                    'ServiceUnavailableException', 'InternalServerException',
                    'ModelNotReadyException', 'ModelTimeoutException'}


def call_with_retry(call, *, attempts=3, sleep=time.sleep, jitter=random.uniform):
    if not 1 <= attempts <= 3:
        raise ValueError('attempts must be between 1 and 3')
    for attempt in range(attempts):
        try:
            return call()
        except Exception as error:
            if attempt == attempts - 1 or not should_retry(error):
                raise
            sleep(jitter(0, min(2.0, 0.25 * 2 ** attempt)))


class VendorSchemaError(ValueError):
    """The initial response and the single repair both failed validation."""
