from anynet import tls, http
import pkg_resources
import ormsgpack
import urllib.parse

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
		if req.method == "POST":
			if len(req.body) != 88:
				raise ValueError("ID and or Password doesn't have the right size")
			req.headers["Content-Length"] = 88
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
		#print(data)
		#this has to be hacky, because I couldn't get proper formatting of the id in the msgpack (uint64 <-> int64; check https://github.com/msgpack/msgpack/blob/master/spec.md)
		req.body = ormsgpack.packb(data).replace(b'\xcf',b'\xd3')
		response = await self.request(req, access_token, MODULE_ENS)
		self.auth_token = ormsgpack.unpackb(response.body)["token"]
		#print(self.auth_token)
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
		print(ormsgpack.unpackb(response.body))
		return response.body
	
	async def download_dream(self, dream_id):
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

		if(searchresult["count"] != 1):
			return 0
		
		req1 = http.HTTPRequest.get(searchresult["dreams"][0]["contents"][0]["url"])
		BodyData = await self.request(req1, None, MODULE_ENS)
		#print(searchresult["dreams"][0]["contents"][0]["url"])
		req2 = http.HTTPRequest.get(searchresult["dreams"][0]["meta"])
		meta = await self.request(req2, None, MODULE_ENS)

		return BodyData.body, ormsgpack.unpackb(meta.body)
        