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

SUPPORTED_CURRENCIES = ("IRR",)
DEFAULT_PAYMENT_METHOD_CODES = {"shetab"}
