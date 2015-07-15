import json
import uuid

import eventlet
from eventlet.event import Event
from eventlet.queue import Queue
from eventlet import wsgi

import webob
from webob.exc import HTTPNotFound

class PublicRequest(object):
    
    def __init__(self, id, request, event):
        self.id = id
        self._request = request
        self.event = event

    @property
    def url(self):
        return self._request.url

    @property
    def environ(self):
        return self._request.environ

    @property
    def body(self):
        return self._request.body


class RequestRegistry(object):
    
    def __init__(self, outgoing):
        self.queue = outgoing
    
    def enqueue_request(self, request):
        request_id = uuid.uuid4()
        request_evt = Event()
        public_req = PublicRequest(request_id, request, request_evt)
        self.queue.put(public_req)
        return request_evt
    
    def dequeue_request(self):
        public_req = self.queue.get()
        return public_req
    
    
class PublicApp(object):
    
    def __init__(self, requests):
        self._requests = requests
    
    def __call__(self, environ, start_response):
        request = webob.Request(environ)
        request_evt = self._requests.enqueue_request(request)
        response_dict = request_evt.wait()
        response = webob.Response(response_dict['body'],
                                  headerlist=response_dict['headers'])
        return response(environ, start_response)


class CommandApp(object):
    
    def __init__(self, requests):
        self._requests = requests
        self._events = {}
    
    def __call__(self, environ, start_response):
        request = webob.Request(environ)
        if request.method != 'POST':
            return HTTPNotFound()(environ, start_response)
        
        body = request.json
        request_id = body.get('req_id')
        if request_id and request_id in self._events:
            self._events.pop(request_id).send(body)
        
        proxied_request = self._requests.dequeue_request()
        self._events[proxied_request.id] = proxied_request.event
        response_dict = proxied_request.environ.copy()
        response_dict['url'] = proxied_request.url
        response_dict['body'] = proxied_request.body
        response = webob.Response(json.dumps(response_dict))
        return response(environ, start_response)


class HubServer(object):
    
    def __init__(self, public_addr, control_addr):
        outgoing_requests = Queue()
        self.requests = RequestRegistry(outgoing_requests)
        public_greenlet = self._start_public_interface(public_addr)
        command_greenlet = self._start_command_interface(control_addr)
        public_greenlet.wait()
        command_greenlet.wait()
    
    def _start_public_interface(self, addr):
        print "public", addr
        server = eventlet.listen(addr)
        app = PublicApp(self.requests)
        return eventlet.spawn(wsgi.server, server, app)
    
    def _start_command_interface(self, addr):
        print "command", addr
        server = eventlet.listen(addr)
        app = CommandApp(self.requests)
        return eventlet.spawn(wsgi.server, server, app)
