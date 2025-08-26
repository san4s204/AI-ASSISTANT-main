import yookassa
from yookassa import Payment
import uuid
from config import ACCOUNT_ID, SECRET_KEY, CRYPTOTOKEN
from aiosend import CryptoPay, TESTNET

yookassa.Configuration.account_id = ACCOUNT_ID
yookassa.Configuration.secret_key = SECRET_KEY
cp = CryptoPay(CRYPTOTOKEN, TESTNET)

def create(amount, chat_id):
    id_key = str(uuid.uuid4())
    payment = Payment.create({
        "amount": {
            'value': amount,
            'currency': "RUB"

        },
        'payment_method_data': {
            'type': 'bank_card'
        },
        'confirmation': {
            'type':'redirect',
            'return_url': 'https://t.me/ot21_test_bot'
        },
        'capture': True,
        'metadata': {
            'chat_id': chat_id
        },
        'description': 'Opisanie'
    }, id_key)

    return payment.confirmation.confirmation_url, payment.id

def check(payment_id):
    payment = yookassa.Payment.find_one(payment_id)
    if payment.status == 'succeeded':
        return payment.metadata
    else:
        return False

async def cript(invoice_id):
    a = str(await cp.get_invoice(invoice_id))
    print(a)
    try:
        if a.split(' ')[7] == 'paid_amount=1.0':
            print('Yes')
            print(a.split()[7])
            return 'Yes'
        else:
            return False
    except:
        return False
