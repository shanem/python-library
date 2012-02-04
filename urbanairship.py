"""Python module for using the Urban Airship API"""

import httplib
import urllib
try:
    import json
except ImportError:
    import simplejson as json


SERVER = 'go.urbanairship.com'
BASE_URL = "https://go.urbanairship.com/api"
DEVICE_TOKEN_URL = BASE_URL + '/device_tokens/'
APID_URL = BASE_URL + '/apids/'
PUSH_URL = BASE_URL + '/push/'
BATCH_PUSH_URL = BASE_URL + '/push/batch/'
BROADCAST_URL = BASE_URL + '/push/broadcast/'
FEEDBACK_URL = BASE_URL + '/device_tokens/feedback/'
ANDROID_FEEDBACK_URL = BASE_URL + '/apids/feedback/'

IOS = 'ios'
ANDROID = 'android'

class UnrecognizedMobilePlatformException(Exception):
    """Raised when a bad "platform" parameter is passed"""

class Unauthorized(Exception):
    """Raised when we get a 401 from the server"""


class AirshipFailure(Exception):
    """Raised when we get an error response from the server.

    args are (status code, message)

    """


class AirshipDeviceList(object):
    """Iterator that fetches and returns a list of device tokens

    Follows pagination

    """

    def __init__(self, airship, platform=IOS):
        self._airship = airship
        self.platform = platform
        if self.platform == IOS:
            self._load_page(DEVICE_TOKEN_URL)
        elif self.platform == ANDROID:
            self._load_page(APID_URL)
        else:
            raise UnrecognizedMobilePlatformException(str(platform))

    def __iter__(self):
        return self

    def next(self):
        try:
            return self._token_iter.next()
        except StopIteration:
            self._fetch_next_page()
            return self._token_iter.next()

    def __len__(self):
        if self.platform == IOS:
            return self._page['device_tokens_count']
        elif self.platform == ANDROID:
            return self._page['apids_count']
        else:
            raise UnrecognizedMobilePlatformException(str(platform))

    def _fetch_next_page(self):
        next_page = self._page.get('next_page')
        if not next_page:
            return
        self._load_page(next_page)

    def _load_page(self, url):
        status, response = self._airship._request('GET', None, url)
        if status != 200:
            raise AirshipFailure(status, response)
        self._page = page = json.loads(response)
        if self.platform == IOS:
            self._token_iter = iter(page['device_tokens'])
        elif self.platform == ANDROID:
            self._token_iter = iter(page['apids'])
        else:
            raise UnrecognizedMobilePlatformException(str(platform))


class Airship(object):

    def __init__(self, key, secret):
        self.key = key
        self.secret = secret

        self.auth_string = ('%s:%s' % (key, secret)).encode('base64')[:-1]

    def _request(self, method, body, url, content_type=None):
        h = httplib.HTTPSConnection(SERVER)
        headers = {
            'authorization': 'Basic %s' % self.auth_string,
        }
        if content_type:
            headers['content-type'] = content_type
        h.request(method, url, body=body.encode('utf8'), headers=headers)
        resp = h.getresponse()
        if resp.status == 401:
            raise Unauthorized(resp.read())

        return resp.status, resp.read()

    def register(self, token, alias=None, tags=None, badge=None, platform=IOS):
        """Register the device token with UA."""
        if platform == IOS:
            url = DEVICE_TOKEN_URL + token
        elif platform == ANDROID:
            url = APID_URL + token
        payload = {}
        if alias is not None:
            payload['alias'] = alias
        if tags is not None:
            payload['tags'] = tags
        if badge is not None:
            payload['badge'] = badge
        if payload:
            body = json.dumps(payload, separators=(',',':'), ensure_ascii=False)
            content_type = 'application/json'
        else:
            body = ''
            content_type = None

        status, response = self._request('PUT', body, url, content_type)
        if not status in (200, 201):
            raise AirshipFailure(status, response)
        return status == 201

    def deregister(self, token, platform=IOS):
        """Mark this device token as inactive"""
        if platform == IOS:
            url = DEVICE_TOKEN_URL + token
        elif platform == ANDROID:
            url = APID_URL + token
        else:
            raise UnrecognizedMobilePlatformException(str(platform))
        status, response = self._request('DELETE', '', url, None)
        if status != 204:
            raise AirshipFailure(status, response)

    def get_device_token_info(self, device_token):
        """Retrieve information about this device token"""
        url = DEVICE_TOKEN_URL + device_token
        status, response = self._request('GET', None, url)
        if status == 404:
            return None
        elif status != 200:
            raise AirshipFailure(status, response)
        return json.loads(response)

    def get_device_tokens(self, platform=IOS):
        return AirshipDeviceList(self, platorm)

    def build_push_payload(self, alert, extra=None, tokens=None, aliases=None, tags=None, platform=IOS, badge=None, sound=None):
        payload = dict()
        if platform == ANDROID:
            payload['android'] = dict()
        elif platform == IOS:
            payload['aps'] = dict()
        if tokens:
            if platform == IOS:
                payload['device_tokens'] = tokens
            elif platform == ANDROID:
                payload['apids'] = tokens
            else:
                raise UnrecognizedMobilePlatformException(str(platform))
        if aliases:
            payload['aliases'] = aliases
        if tags:
            payload['tags'] = tags
        if alert:
            if platform == ANDROID:
                payload['android']['alert'] = alert
            elif platform == IOS:
                payload['aps']['alert'] = alert
        if sound:
            if platform == IOS:
                payload['aps']['sound'] = sound
        if badge:
            if platform == IOS:
                payload['aps']['badge'] = badge
        if extra:
            if platform == IOS:
                payload['d'] = extra
            elif platform == ANDROID:
                payload['android']['extra'] = extra
            else:
                raise UnrecognizedMobilePlatformException(str(platform))
        return payload

    def push(self, alert, extra=None, tokens=None, aliases=None, tags=None, platform=IOS, badge=None, sound=None):
        """Push this payload to the specified device tokens and tags."""
        payload = self.build_push_payload(alert, extra, tokens, aliases, tags, platform, badge, sound)
        body = json.dumps(payload, separators=(',',':'), ensure_ascii=False)
        status, response = self._request('POST', body, PUSH_URL,
            'application/json')
        if not status == 200:
            raise AirshipFailure(status, response)

    def push_batch(self, payloads):
        body = json.dumps(payloads, separators=(',',':'), ensure_ascii=False)
        status, response = self._request('POST', body, BATCH_PUSH_URL, 'application/json')
        if not status == 200:
            raise AirshipFailure(status, response)

    def broadcast(self, payload, exclude_tokens=None):
        """Broadcast this payload to all users."""
        if exclude_tokens:
            payload['exclude_tokens'] = exclude_tokens
        body = json.dumps(payload, separators=(',',':'), ensure_ascii=False)
        status, response = self._request('POST', body, BROADCAST_URL,
            'application/json')
        if not status == 200:
            raise AirshipFailure(status, response)

    def feedback(self, since):
        """Return device tokens marked inactive since this timestamp.

        Returns a list of (device token, timestamp, alias) functions.

        Example:
            airship.feedback(datetime.datetime.utcnow()
                - datetime.timedelta(days=1))

        Note:
            In order to parse the result, we need a sane date parser,
            dateutil: http://labix.org/python-dateutil

        """
        url = FEEDBACK_URL + '?' + \
            urllib.urlencode({'since': since.isoformat()})
        status, response = self._request('GET', '', url)
        if not status == 200:
            raise AirshipFailure(status, response)
        data = json.loads(response)
        try:
            from dateutil.parser import parse
        except ImportError:
            def parse(x):
                return x
        return [
            (r['device_token'], parse(r['marked_inactive_on']), r['alias'])
            for r in data]
