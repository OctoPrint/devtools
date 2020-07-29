# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
import json

class GithubReleasePatcherPlugin(octoprint.plugin.StartupPlugin,
                                 octoprint.plugin.SettingsPlugin):
	def __init__(self):
		self._server = None
		self._thread = None

	def on_after_startup(self):
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

		import BaseHTTPServer
		import SimpleHTTPServer
		import random

		releases = self._settings.get(["releases"])

		class ReleaseHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
			def do_GET(self):
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
					if not key in releases:
						self.send_response(404)
						return

					release_list = releases[key]
					self.send_response(200)
					self.send_header("Content-Type", "application/json")
					self.end_headers()
					json.dump(release_list, self.wfile)

		server_port = self._settings.get_int(["port"])
		for _ in xrange(10):
			if server_port:
				try:
					self._server = BaseHTTPServer.HTTPServer(("127.0.0.1", server_port), ReleaseHandler)
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

__plugin_name__ = "Github release patcher"
__plugin_version__ = "0.1.0"
__plugin_description__ = "Patches the Github release API endpoint to point to some local service"
__plugin_implementation__ = GithubReleasePatcherPlugin()
