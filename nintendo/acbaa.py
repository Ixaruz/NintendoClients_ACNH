from anynet import tls, http
import pkg_resources
import ormsgpack
import urllib.parse
from time import sleep
from random import uniform
import json

import logging
logger = logging.getLogger(__name__)

CA = pkg_resources.resource_filename("nintendo", "files/cert/CACERT_NINTENDO_CA_G3.der")

MODULE_ENS = "nnEns"

USER_AGENT = {
	0x00020000: "libcurl/7.64.1 (HAC; %s; SDK 9.3.3.0)",    #1.1.1
	0x00050000: "libcurl/7.64.1 (HAC; %s; SDK 9.3.3.0)",    #1.1.4
	0x00060000: "libcurl/7.64.1 (HAC; %s; SDK 9.3.4.0)",    #1.2.0
	0x00130000: "libcurl/7.64.1 (HAC; %s; SDK 10.9.3.0)",   #1.10.0
	0x00160000: "libcurl/7.64.1 (HAC; %s; SDK 10.9.8.0)",   #2.0.0
	0x00170000: "libcurl/7.64.1 (HAC; %s; SDK 10.9.8.0)",   #2.0.1
	0x00180000: "libcurl/7.64.1 (HAC; %s; SDK 10.9.8.0)",   #2.0.2
	0x00190000: "libcurl/7.64.1 (HAC; %s; SDK 10.9.8.0)",   #2.0.3
	0x001A0000: "libcurl/7.64.1 (HAC; %s; SDK 10.9.8.0)",   #2.0.4
	0x001B0000: "libcurl/7.64.1 (HAC; %s; SDK 10.9.8.0)",   #2.0.5
    0x001C0000: "libcurl/7.64.1 (HAC; %s; SDK 10.9.8.0)",   #2.0.6
}

LATEST_VERSION = 0x001C0000

class ACBAAClient:
	def __init__(self):
		self.request_callback = http.request
		
		self.context = tls.TLSContext()
		ca = tls.TLSCertificate.load(CA, tls.TYPE_DER)
		self.context = tls.TLSContext()
		self.context.set_authority(ca)


		self.host = "api.hac.lp1.acbaa.srv.nintendo.net"
		self.auth_token = ""
		self.user_agent = USER_AGENT[LATEST_VERSION]
	
	def set_request_callback(self, callback): self.request_callback = callback
	def set_context(self, context): self.context = context
	
	def set_host(self, host): self.host = host
	def set_power_state(self, state): self.power_state = state
	
	def set_title_version(self, version):
		if version not in USER_AGENT:
			raise ValueError("Unknown title version")
		self.user_agent = USER_AGENT[version]
		
	async def request(self, req, token, module):
		req.headers["Host"] = self.host
		req.headers["User-Agent"] = self.user_agent %module
		req.headers["Accept"] = "*/*"
		if token:
			req.headers["Authorization"] = "Bearer " + token
			req.headers["Content-Type"] = "application/x-msgpack"
		if req.method == "POST" or req.method == "PUT":
			if req.body is None:
				raise ValueError("req.body can't be empty when using POST")
			req.headers["Content-Length"] = len(req.body)
		if module != MODULE_ENS:
			raise NotImplementedError("Unknown Module")
		
		response = await self.request_callback(self.host, req, self.context)
		# if response.body and "errorCode" in response.body:
		# 	logger.warning("ACBAA server returned an error: %s" %response.body)
		# 	raise NotImplementedError("ACBAA server returned an error")
		# response.raise_if_error()
		return response
	
	async def authenticate(self, id, password, access_token):
		req = http.HTTPRequest.post("/api/v1/auth_token")
		data = {
			"id": id,
			"password": password
		}
		#this has to be hacky, because I couldn't get proper formatting of the id in the msgpack (uint64 <-> int64; check https://github.com/msgpack/msgpack/blob/master/spec.md)
		req.body = ormsgpack.packb(data).replace(b'\xcf',b'\xd3')
		if len(req.body) != 88:
			raise ValueError("ID and or Password doesn't have the right size")
		response = await self.request(req, access_token, MODULE_ENS)
		self.auth_token = ormsgpack.unpackb(response.body)["token"]
		return response.body
	
	async def search_dream_by_id(self, dream_id):
		if self.auth_token == "":
			return
		
		url = "/api/v1/dream_lands"
		
		string_query = {
			"offset" : 0,
			"limit" : 150,
			"q[id]" : dream_id
		}

		url_parts = urllib.parse.urlparse(url)
		query = dict(urllib.parse.parse_qsl(url_parts.query))
		query.update(string_query)
		new_url = url_parts._replace(query=urllib.parse.urlencode(query)).geturl()

		req = http.HTTPRequest.get(new_url)

		response = await self.request(req, self.auth_token, MODULE_ENS)
		searchresult = ormsgpack.unpackb(response.body)
		return searchresult
	
	async def download_dream_by_id(self, dream_id):
		# mimic the game's behavior; it searches and gets metadata, 
		# then sends feedback and waits for user input
		# to confirm and search again to download the metadata and dream properly
		searchresult = await self.search_dream_by_id(dream_id)
		http.HTTPRequest.get(searchresult["dreams"][0]["meta"])
		req = await self.send_feedback_id_search(dream_id)
		sleep(uniform(5.0, 12.0))
		searchresult = await self.search_dream_by_id(dream_id)
		
		#if not one dream is found
		if(searchresult["count"] != 1):
			logger.warning("Search for dream address ended with an unexpected response")
			return 0, 0
		
		logger.info(json.dumps(searchresult, indent=2))

		req1 = http.HTTPRequest.get(searchresult["dreams"][0]["meta"])
		meta = await self.request(req1, None, MODULE_ENS)
		req2 = http.HTTPRequest.get(searchresult["dreams"][0]["contents"][0]["url"])
		BodyData = await self.request(req2, None, MODULE_ENS)

		return BodyData.body, ormsgpack.unpackb(meta.body)

	# idk how necessary this function is, though it's best to send feedback after searching for a dream
	async def send_feedback_id_search(self, dream_id):
		if self.auth_token == "":
			return
		
		req = http.HTTPRequest.post("/api/v1/dream_lands/%s/feedback" %dream_id)
		
		data = {
			"kind" : "id_search"
		}

		req.body = ormsgpack.packb(data)
		response = await self.request(req, self.auth_token, MODULE_ENS)
		return response
	
	async def get_friends(self):
		if self.auth_token == "":
			return
		
		req = http.HTTPRequest.get("/api/v1/friends")
		response = await self.request(req, self.auth_token, MODULE_ENS)
		friends = ormsgpack.unpackb(response.body)
		return friends
        