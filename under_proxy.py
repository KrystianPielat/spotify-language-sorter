from flask import Flask
import os

PREFIX = os.environ["PREFIX"] if os.environ.get("PREFIX") else ""


class PrefixMiddleware(object):
    def __init__(self, app, prefix=""):
        self.app = app
        self.prefix = prefix

    def __call__(self, environ, start_response):

        if environ["PATH_INFO"].startswith(self.prefix):
            environ["PATH_INFO"] = environ["PATH_INFO"][len(self.prefix) :]
            environ["SCRIPT_NAME"] = self.prefix
            return self.app(environ, start_response)
        else:
            start_response("404", [("Content-Type", "text/plain")])
            return ["This url does not belong to the app.".encode()]


def get_flask_app(prefix=None):
    app = Flask(__name__)
    if prefix:
        app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix=prefix)
    else:
        app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix=PREFIX)

    return app
