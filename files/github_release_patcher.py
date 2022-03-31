# coding=utf-8
from __future__ import absolute_import, unicode_literals, print_function

import octoprint.plugin
import json
import requests

class GithubReleasePatcherPlugin(octoprint.plugin.StartupPlugin,
                                 octoprint.plugin.SettingsPlugin):
    def __init__(self):
        self._server = None
        self._thread = None

    def on_after_startup(self):
        self._logger.info("Starting up GithubReleasePatcherPlugin...")

        import threading

        self._thread = threading.Thread(target=self._patch)
        self._thread.daemon = True
        self._thread.start()

    def get_settings_defaults(self):
        return dict(releases=dict(),
                    port=None)

    def _patch(self):
        try:
            from softwareupdate.version_checks import github_release
        except:
            try:
                from octoprint.plugins.softwareupdate.version_checks import github_release
            except:
                self._logger.exception("Could not import github_release version_checker for patching")
                return

        try:
            from http.server import BaseHTTPRequestHandler, HTTPServer
        except ImportError:
            from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler

        import random

        releases = self._settings.get(["releases"], merged=True)
        self._logger.info("Found {} patched releases entries:\n{!r}".format(len(releases), releases))

        orig_release_url = github_release.RELEASE_URL

        class ReleaseHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                import logging
                logger = logging.getLogger("octoprint.plugins.github_release_patcher.ReleaseHandler")

                split_path = self.path.split("/")
                if not len(split_path) == 4:
                    self.send_response(404)
                    return

                _, base, user, repo = split_path
                if not base in ("releases",):
                    self.send_response(404)
                    return

                if base == "releases":
                    key = "{}/{}".format(user, repo)
                    headers = {}

                    if key in releases:
                        logger.info("Returning patched release information for {}/{}".format(user, repo))
                        release_list = releases[key]
                    else:
                        logger.info("Fetching original release information for {}/{}".format(user, repo))
                        r = requests.get(orig_release_url.format(user=user, repo=repo))
                        if r.status_code != 200:
                            self.send_response(r.status_code)
                            return
                        release_list = r.json()
                        for header in ("X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"):
                            if header in r.headers:
                                headers[header] = r.headers[header]

                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    for header, value in headers.items():
                        self.send_header(header, value)
                    self.end_headers()

                    output = json.dumps(release_list).encode("utf-8")
                    self.wfile.write(output)

        server_port = self._settings.get_int(["port"])
        for _ in range(10):
            if server_port:
                try:
                    self._server = HTTPServer(("127.0.0.1", server_port), ReleaseHandler)
                    self._logger.info("Started dummy release server on http://127.0.0.1:{}".format(server_port))
                    break
                except:
                    self._logger.exception("Hm, nope, port {} didn't work...".format(server_port))
            server_port = random.randrange(1025, 65535)
        else:
            self._logger.error("Could not find a free port for my dummy release endpoint")
            return

        url = "http://127.0.0.1:{}".format(server_port)
        url += "/releases/{user}/{repo}"
        github_release.RELEASE_URL = url

        self._logger.info("Set Github release URL to {}".format(url))

        self._server.serve_forever()

__plugin_name__ = "GitHub release patcher"
__plugin_version__ = "0.3.0"
__plugin_pythoncompat__ = ">=2.7,<4"
__plugin_description__ = "Patches the GitHub release API endpoint to point to some local service"
__plugin_implementation__ = GithubReleasePatcherPlugin()
