
from nintendo.baas import BAASClient
from nintendo.dauth import DAuthClient
from nintendo.aauth import AAuthClient
from nintendo.dragons import DragonsClient
from nintendo.acbaa import ACBAAClient
from nintendo.nex import backend, authentication, matchmaking, settings
from nintendo import switch
import anyio
import os

import logging
logging.basicConfig(level=logging.INFO)


SYSTEM_VERSION = 1603 #16.0.3

# You can get your user id and password from
# su/baas/<guid>.dat in save folder 8000000000000010.

# Bytes 0x20 - 0x28 contain the user id in reversed
# byte order, and bytes 0x28 - 0x50 contain the
# password in plain text.

# Alternatively, you can set up a mitm on your Switch
# and extract them from the request to /1.0.0/login

BAAS_USER_ID = 0x0123456789abcdef # 16 hex digits
BAAS_PASSWORD = "..." # Should be 40 characters

# You can dump prod.keys with Lockpick_RCM and
# PRODINFO from hekate (decrypt it if necessary)
PATH_KEYS = "/path/to/prod.keys"
PATH_PRODINFO = "/path/to/PRODINFO"

# These can be obtained by calling publish_device_linked_elicenses (see docs)
# or with a mitm on your Switch (this is probably safer)
ELICENSE_ID = "..." # 32 hex digits
NA_ID = 0x0123456789abcdef # 16 hex digits

DREAM_ID = 0
DREAM_ID_TEXT = 'DA-' + '-'.join([f'{DREAM_ID:012d}'[index:index+4]for index in range(0, 12, 4)])

TITLE_ID = 0x01006F8002326000
TITLE_VERSION = 0x001C0000


# can be found in the decrypted main.dat or personal.dat
# of your animal crossing save file.
## for 2.0.0 save files ##
# main.dat.dec (addresses for Villager0): 
# Bytes 0x8CD8F8 - 0x8CD900 contain the user id
# Bytes 0x8CD900 - 0x8CD940 contain the password in plain text
# personal.dat.dec:
# Bytes 0x5C960 - 0x5C968 contain the user id
# Bytes 0x5C968 - 0x5C9A8 contain the password in plain text

# just like BAAS user_id and password, you can get 
# these by setting up a mitm on your switch and
# extract them from the request to /api/v1/auth_token.
# They are packed in the (application/x-msgpack) format.

ACBAA_ID = 0x0123456789abcdef # 16 hex digits also known as mMtNsaId
ACBAA_PASSWORD = "..." # 64 hex digits

async def main():
	keys = switch.load_keys(PATH_KEYS)
	
	info = switch.ProdInfo(keys, PATH_PRODINFO)
	cert = info.get_tls_cert()
	pkey = info.get_tls_key()
	
	dauth = DAuthClient(keys)
	dauth.set_certificate(cert, pkey)
	dauth.set_system_version(SYSTEM_VERSION)
	
	dragons = DragonsClient()
	dragons.set_certificate(cert, pkey)
	dragons.set_system_version(SYSTEM_VERSION)
	
	aauth = AAuthClient()
	aauth.set_system_version(SYSTEM_VERSION)
	
	baas = BAASClient()
	baas.set_system_version(SYSTEM_VERSION)
	
	acbaa = ACBAAClient()
	acbaa.set_title_version(TITLE_VERSION)

	# Request a device authentication token for dragons
	response = await dauth.device_token(dauth.DRAGONS)
	device_token_dragons = response["device_auth_token"]
	
	# Request a device authentication token for aauth and bass
	response = await dauth.device_token(dauth.BAAS)
	device_token_baas = response["device_auth_token"]
	
	# Request a contents authorization token from dragons
	response = await dragons.contents_authorization_token_for_aauth(device_token_dragons, ELICENSE_ID, NA_ID, TITLE_ID)
	contents_token = response["contents_authorization_token"]
	
	# Request an application authentication token
	response = await aauth.auth_digital(TITLE_ID, TITLE_VERSION, device_token_baas, contents_token)
	app_token = response["application_auth_token"]
	
	# Request an anonymous access token for baas
	response = await baas.authenticate(device_token_baas)
	access_token = response["accessToken"]
	
	# Log in on the baas server
	response = await baas.login(
		BAAS_USER_ID, BAAS_PASSWORD, access_token, app_token
	)

	user_id = int(response["user"]["id"], 16)
	id_token = response["idToken"]

	response = await acbaa.authenticate(ACBAA_ID, ACBAA_PASSWORD, id_token)

	Body, meta = await acbaa.download_dream_by_id(DREAM_ID)


	if not (os.path.isdir(DREAM_ID_TEXT)): os.mkdir(DREAM_ID_TEXT)

	f = open(DREAM_ID_TEXT + "/dreamdownload.dat", "wb")
	f.write(Body)
	f.close()

	f = open(DREAM_ID_TEXT + "/dreammeta.txt", "w")
	f.write(str(meta))
	f.close()
	

anyio.run(main)