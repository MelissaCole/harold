import hashlib
import hmac
import urlparse

from twisted.web import resource, server
from twisted.application import internet
from twisted.internet import reactor
from twisted.internet.endpoints import serverFromString

from harold.plugin import Plugin
from harold.conf import PluginConfig, Option


def constant_time_compare(actual, expected):
    """
    Returns True if the two strings are equal, False otherwise

    The time taken is dependent on the number of characters provided
    instead of the number of characters that match.
    """
    actual_len = len(actual)
    expected_len = len(expected)
    result = actual_len ^ expected_len
    if expected_len > 0:
        for i in xrange(actual_len):
            result |= ord(actual[i]) ^ ord(expected[i % expected_len])
    return result == 0


class HttpConfig(PluginConfig):
    endpoint = Option(str)
    secret = Option(str)
    hmac_secret = Option(str, default=None)
    public_root = Option(str, default="")


class AuthenticationError(Exception):
    pass


class ProtectedResource(resource.Resource):
    def __init__(self, http):
        self.http = http

    def render_POST(self, request):
        try:
            HEADER_NAME = "X-Hub-Signature"
            has_signature = request.requestHeaders.hasHeader(HEADER_NAME)
            if self.http.hmac_secret and has_signature:
                # modern method: hmac of request body
                body = request.content.read()
                expected_hash = hmac.new(
                    self.http.hmac_secret, body, hashlib.sha1).hexdigest()

                header = request.requestHeaders.getRawHeaders(HEADER_NAME)[0]
                hashes = urlparse.parse_qs(header)
                actual_hash = hashes["sha1"][0]

                if not constant_time_compare(expected_hash, actual_hash):
                    raise AuthenticationError
            elif request.postpath:
                # old method: secret token appended to request url. deprecated.
                secret = request.postpath.pop(-1)
                if not constant_time_compare(secret, self.http.secret):
                    raise AuthenticationError
            else:
                # no further authentication methods
                raise AuthenticationError
        except AuthenticationError:
            request.setResponseCode(403)
        else:
            self._handle_request(request)

        return ""


def make_plugin(config):
    http_config = HttpConfig(config)

    root = resource.Resource()
    harold = resource.Resource()
    root.putChild('harold', harold)
    site = server.Site(root)
    site.displayTracebacks = False

    endpoint = serverFromString(reactor, http_config.endpoint)
    service = internet.StreamServerEndpointService(endpoint, site)

    plugin = Plugin()
    plugin.root = harold
    plugin.secret = http_config.secret
    plugin.hmac_secret = http_config.hmac_secret
    plugin.add_service(service)

    return plugin
