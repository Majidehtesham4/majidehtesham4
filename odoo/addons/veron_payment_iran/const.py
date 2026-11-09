"""The gateways' addresses and answers, as their documentation gives them"""

ZARINPAL = {
	# provider state: (API, payment page)
	"enabled": ("https://payment.zarinpal.com/pg/v4/payment/", "https://payment.zarinpal.com/pg/StartPay/"),
	"test": ("https://sandbox.zarinpal.com/pg/v4/payment/", "https://sandbox.zarinpal.com/pg/StartPay/"),
}
# 100: paid and verified now; 101: already verified (the page was opened twice)
ZARINPAL_PAID = (100, 101)

ZIBAL_API = "https://gateway.zibal.ir/v1/"
ZIBAL_START = "https://gateway.zibal.ir/start/"
# Zibal's own test merchant: payments that are simulated, never charged
ZIBAL_TEST_MERCHANT = "zibal"
# 100: paid and verified now; 201: already verified
ZIBAL_PAID = (100, 201)

# Behpardakht Mellat (bpm.shaparak.ir): a SOAP service; the customer is sent to the payment page with a POST
MELLAT_API = "https://bpm.shaparak.ir/pgwchannel/services/pgw"
MELLAT_START = "https://bpm.shaparak.ir/pgwchannel/startpay.mellat"
MELLAT_NAMESPACE = "http://interfaces.core.sw.bps.com/"
# 0: done; 43: verified before; 45: settled before
MELLAT_OK, MELLAT_VERIFIED, MELLAT_SETTLED = "0", "43", "45"

# Sadad of Bank Melli (sadad.shaparak.ir): each request signed with the merchant's key (Triple DES)
SADAD_REQUEST = "https://sadad.shaparak.ir/api/v0/Request/PaymentRequest"
SADAD_VERIFY = "https://sadad.shaparak.ir/api/v0/Advice/Verify"
SADAD_START = "https://sadad.shaparak.ir/Purchase?token="

# Asan Pardakht (asanpardakht.ir): its REST service, with the merchant's user and password in the headers
ASAN_API = "https://ipgrest.asanpardakht.ir/v1/"
ASAN_START = "https://asan.shaparak.ir"

# Every gateway of this module
CODES = ("zarinpal", "zibal", "mellat", "sadad", "asanpardakht")
BANKS = ("mellat", "sadad", "asanpardakht")

SUPPORTED_CURRENCIES = ("IRR",)
DEFAULT_PAYMENT_METHOD_CODES = {"shetab"}
