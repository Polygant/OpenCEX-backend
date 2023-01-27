# Auth
Each HMAC requests expect the following HTTP Headers:  
**APIKEY** - Your API Key.  
**SIGNATURE** - An HMAC-SHA256 hash of the nonce concatenated with API KEY and login of the HTTP request, signed using your API secret.  
**NONCE** - Timestamp in milliseconds.  

* **Example**
```python
import requests
from pprint import pprint
import hashlib
import hmac
import time

def make_request(uri, data=None):
    url = 'https://example.com/api/public/v1/' + uri
    nonce = str(int(round(time.time() * 1000)))
    api_key = '<YOUR API KEY>'
    secret_key = '<YOUR SECRET KEY>'
    message = api_key + nonce
    signature = hmac.new(
        secret_key.encode(),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest().upper()
    headers = {
        'APIKEY': api_key,
        'SIGNATURE': signature,
        'NONCE': nonce
    }
    if data:
        res = requests.post(url, headers=headers, json=data)
    else:
        res = requests.get(url, headers=headers)
    return res
```

# Common reponse status codes

  `429` - Too many requests per second. Max 2 requests per second. 


# Endpoints
**Summary**
----
  Overview of market data for all tickers.

* **URL**  

  /api/public/v1/summary

* **Method:**  

  `GET`
  
* **URL Params**  

  None

* **Data Params**  

  None

* **Success Response:**  
```json
{
    "data": {        
        "BTC_USD": {
            "last_price": 9503.364483,
            "high_24h": 9519.215928,
            "low_24h": 9475.8597,
            "base_volume": 0.20381013,
            "quote_volume": 1934.88922435,
            "lowest_ask": 9503.364483,
            "highest_bid": 9475.8597,
            "percent_change": 0.0345,
            "is_frozen": 0
        },
        ...
    },
    "coins": {
        "BTC": {
            "name": "Bitcoin",
            "withdraw": "ON",
            "deposit": "ON"
        },
        "ETH": {
            "name": "Ethereum",
            "withdraw": "ON",
            "deposit": "ON"
        },
        ...
    }
}
```

* **Response status codes**  

  `200` - OK


**Assets list**
----
  Returns assets list

* **URL**  

  /api/public/v1/assets

* **Method:**  

  `GET`
  
* **URL Params**  

  None

* **Data Params**  

  None

* **Success Response:**  
```json
{
    "BTC": {
        "name": "Bitcoin"
    },
    "ETH": {
        "name": "Ethereum"
    },
    "USDT": {
        "name": "Tether"
    },
    ...
}
```

* **Response status codes**  

  `200` - OK


**Markets list**
----
  Returns markets list

* **URL**  

  /api/public/v1/markets

* **Method:**  

  `GET`
  
* **URL Params**  

  None

* **Data Params**  

  None

* **Success Response:**  
```json
[
    {
        "id": "ETH-BTC",
        "base": "ETH",
        "quote": "BTC"
    },
    {
        "id": "ETH-USD",
        "base": "ETH",
        "quote": "USD"
    },
    ...
]
```

* **Response status codes**  

  `200` - OK



**Tickers**  
----

  Returns stats of markets.

* **URL**  

  /api/public/v1/ticker

* **Method:**  

  `GET`
  
* **URL Params**  

  None

* **Data Params**  

  None

* **Success Response:**  

```json
{
    "ETH_BTC": {
        "last_price": 0.02046117,
        "base_volume": 64.73692076,
        "quote_volume": 1.353921854,
        "is_frozen": 0
    },
    "ETH_USD": {
        "last_price": 198.82570815,
        "base_volume": 266.91056844,
        "quote_volume": 54669.13833,
        "is_frozen": 0
    },
}
```

* **Response status codes**  

  `200` - OK



**Binance BTC-USD price**  
----

  Returns price of BTC-USD from binance.

* **URL**  

  /api/public/v1/otcprice

* **Method:**  

  `GET`
  
* **URL Params**  

  None

* **Data Params**

  None

* **Success Response:**  

```json 
{"price": 5234.32}
```

* **Response status codes**  

  `200` - OK


**Order book**  
----

  Returns the order book of a specified market.

* **URL**  

  /api/public/v1/orderbook/<market_name>

* **Method:**  

  `GET`
  
* **URL Params**  
  
    **Optional:**  
    `depth=[integer]` - number of entries. 100 by default, max. 500

* **Data Params**

  None

* **Success Response:**  

```json 
{
    "timestamp": 1569313042682,
    "asks": [
        [
            9733.685,
            0.00037616
        ]
    ],
    "bids": [
        [
            9733.183,
            0.00030966
        ]
    ]
}
```

* **Response status codes**  

  `200` - OK


**Last Trades**  
----

  Returns recent trades.

* **URL**  

  /api/public/v1/trades/<market_name>

* **Method:**  

  `GET`
  
* **URL Params**  

  None

* **Data Params**

  None

* **Success Response:**  

```json 
[
    {
        "trade_id": 30694469,
        "price": 9724.14488444,
        "base_volume": 0.00038326,
        "quote_volume": 3.7268757684104745,
        "trade_timestamp": 1569313098,
        "type": "buy"
    },
    {
        "trade_id": 30694467,
        "price": 9725.14002299,
        "base_volume": 0.00034305,
        "quote_volume": 3.3362092848867193,
        "trade_timestamp": 1569313098,
        "type": "sell"
    },
    ...
]
```

* **Response status codes**  

  `200` - OK


**Balances (Requires API-KEY)**  
----

  Returns balances of all wallets.  

* **URL**  

  /api/public/v1/balance

* **Method:**  

  `GET`

* **URL Params**

  None

* **Data Params**  

  None

* **Success Response:**  

```json
  {
    "BTC": {
      "actual": 73.59451,
      "orders": 0.40877
    },
    "EUR": {
      "actual": 9821.53659869,
      "orders": 88.51722622
    },
    "USD": {
      "actual": 100078.73854682,
      "orders": 6.61468349
    },
}
```

* **Response status codes**  

  `200` - OK



**Selected wallet balance (Requires API-KEY)**  
----

  Returns balances of selected wallet.

* **URL**  

  /api/public/v1/balance/:wallet_name  (BTC, ETH, USD, etc...)

* **Method:**  

  `GET`

* **URL Params**  

  None

* **Data Params**  

  None

* **Success Response:**  
```json
{
    "currency": "BTC",
    "actual": 73.59498,
    "orders": 0.40855
}
```

* **Response status codes**  

  `200` - OK
  
  `404` - Wallet not found


# Orders  

**Response params**  
----  

`operation` - 0 - Buy, 1 - Sell  
`state` - 0 - Opened, 1 - Closed, 2 - Cancelled  
`type` - 0 - Limit Order  


**Orders list**  
----
  Returns user's orders list.

* **URL**  

  /api/public/v1/order

* **Method:**

  `GET`

* **URL Params**  

   **Optional:**  
   `limit=[integer]` - number of entries  
   `pair=[string]` - pair name (BTC-USD, ETH-USD, etc...)  
   `state=[0|1|2]` - 0 - Opened, 1 - Closed, 2 - Cancelled  
   `operation=[0|1]` - 0 - Buy, 1 - Sell

* **Data Params**

  None

* **Success Response:**

```json
[
    {
        "id": 8467,
        "data": {
            "special_data": {
              "percent": null,
              "limit": null
            }
        },
        "state": 0,
        "pair": "BTC-USD",
        "operation": 0,
        "type": 0,
        "quantity": 0.00048000,
        "price": 5272.67000000,
        "executed": false,
        "quantity_left": 0.00048000,
        "updated": 1555579069649,
        "created": 1555579069649,
        "vwap": 0,
        "otc_percent": null,
        "otc_limit": null,
    },
]
```

* **Response status codes**  

  `200` - OK
  
  `400` - Incorrect query params (details in response)


**Order details**  
----
  Returns order details.

* **URL**  

  /api/public/v1/order/:id

* **Method:**

  `GET`

* **URL Params**  

  None

* **Data Params**

  None

* **Success Response:**

```json
{
    "id": 8467,
    "data": {
      "special_data": {
        "percent": null,
        "limit": null
      }
    },
    "state": 0,
    "pair": "BTC-USD",
    "operation": 0,
    "type": 0,
    "quantity": 0.00048000,
    "price": 5272.67000000,
    "executed": false,
    "quantity_left": 0.00048000,
    "updated": 1555579069649,
    "created": 1555579069649,
    "vwap": 0,
    "otc_percent": null,
    "otc_limit": null,
    "matches": [
      {
        "id": 491569,
        "order_price": 1917.00000000,
        "quantity": 0.00100000
      },
      ...
    ]
}
```

* **Response status codes**  

  `200` - OK
  
  `404` - Order not found



**Create limit order**
----
  Creates new limit order.

* **URL**

  /api/public/v1/order

* **Method:**

  `POST`

* **URL Params**

  None

* **Data Params**  

  **Required:**  
    `type=0` - always 0 for this type of orders  
    `pair=[string]` - pair name (BTC-USD, ETH-USD, etc...)  
    `quantity=[decimal|float]`  
    `price=[decimal|float]`  
    `operation=[0|1]` -  0 - Buy, 1- Sell


* **Success Response:**

```json
{
    "id": 8467,
    "data": {
      "special_data": {
        "percent": null,
        "limit": null
      }
    },
    "state": 0,
    "pair": "BTC-USD",
    "operation": 0,
    "type": 0,
    "quantity": 0.00048000,
    "price": 5272.67000000,
    "executed": false,
    "quantity_left": 0.00048000,
    "updated": 1555579069649,
    "created": 1555579069649,
    "vwap": 0,
    "otc_percent": null,
    "otc_limit": null
}
```

* **Response status codes**  

  `201` - New order created
  
  `400` - Incorrect query params (details in response)
 

**Create OTC order**
----
  Creates new OTC order.

* **URL**

  /api/public/v1/order

* **Method:**

  `POST`

* **URL Params**

  None

* **Data Params**  

  **Required:**  
    `type=2` - always 2 for this type of orders  
    `pair=[string]` - pair name (BTC-USD, ETH-USD, etc...)  
    `quantity=[decimal|float]`
    `operation=[0|1]` -  0 - Buy, 1- Sell
    `otc_percent=[decimal|float]`
    `otc_limit=[decimal|float]`


* **Success Response:**

```json
{
    "id": 8466,
    "data": {
      "special_data": {
        "percent": 2,
        "limit": 5272
      }
    },
    "state": 0,
    "pair": "BTC-USD",
    "operation": 1,
    "type": 2,
    "quantity": 1.00000000,
    "price": 5324.40000000,
    "executed": false,
    "quantity_left": 1.00000000,
    "updated": 1555578754901,
    "created": 1555578754900,
    "vwap": 0,
    "otc_percent": 2.00000000,
    "otc_limit": 5272.00000000
}
```

* **Response status codes**  

  `201` - New order created
  
  `400` - Incorrect query params (details in response)


**Update limit order**  
----
  Updates limit order.

* **URL**

  /api/public/v1/order/:id

* **Method:**

  `PUT`

* **URL Params**

  None

* **Data Params**

  **Required:**  
   `quantity=[decimal|float]`   
   `price=[decimal|float]`

* **Success Response:**

```json
{
    "data": null, 
    "status": 1
}
```

* **Response status codes**  

  `200` - OK
  
  `400` - Incorrect query params (details in response)
  
  `404` - Order not found


**Update OTC order**  
----
  Updates OTC order.

* **URL**

  /api/public/v1/order/:id

* **Method:**

  `PUT`

* **URL Params**

  None

* **Data Params**

  **Required:**  
   `quantity=[decimal|float]`  
   `otc_percent=[decimal|float]`
   `otc_limit=[decimal|float]`

* **Success Response:**

```json
{
    "data": null, 
    "status": 1
}
```

* **Response status codes**  

  `200` - OK
  
  `400` - Incorrect query params (details in response)
  
  `404` - Order not found


**Cancel order**
----
  Cancel order.

* **URL**

  /api/public/v1/order/:id

* **Method:**

  `DELETE`

*  **URL Params**

   None

* **Data Params**

   None

* **Success Response:**

```json
{
    "data": null, 
    "status": 1
}
```

* **Response status codes**  

  `200` - OK
  
  `404` - Order not found


# Orders state callback
* **HEADERS:**  
   `Content-Type: application/json`  
   `APIKEY: <Some API-KEY>`  
   `SIGNATURE: <Some generated signature >`  
   `NONCE: <NONCE>`

* **BODY DATA:**  

```json
{
  "id": 3525, 
  "data": {
    "special_data": {
      "percent": null, 
      "limit": null,
    },
  }, 
  "state": 1, 
  "pair": "BTC-USD", 
  "operation": 0, 
  "type": 0, 
  "quantity": "0.01000000", 
  "price": "1917.48000000", 
  "executed": true, 
  "quantity_left": "0E-8", 
  "updated": 1556289070017, 
  "created": 1556289065082, 
  "vwap": "0E-8", 
  "otc_percent": null, 
  "otc_limit": null,
  "matches": [
    {
      "id": 491569,
      "order_price": 1917.00000000,
      "quantity": 0.00100000
    },
    ...
  ]
}
```

# P2P  

**Get P2P Profile info**  
----
  Returns user's p2p profile info.

* **URL**  

  /api/public/v1/p2p/profile

* **Method:**

  `GET`

* **URL Params**  

   None

* **Data Params**

  None

* **Success Response:**

```json
{
  "fullname": "Nikolay Bereza",
  "nickname": "bereza",
  "user_type": 2,
  "tg_userid": 10000000000,
  "requisites": [
    {
      "id": 12,
      "payment_method": {
        "id": 1,
        "name": "Sepa",
        "logo": "https://example.com/upload/uploads/paymentmethods/logo/social-en_CfqvhgQ.png",
        "fiat_currency": "EUR"
      },
      "requisites": "1111222233334444",
      "holder": "TESTREQ"
    }
  ]
}
```

* **Response status codes**  

  `200` - OK
  
  `400` - Incorrect query params (details in response)


**Change P2P Profile info**  
----
  Changes user's p2p profile info.

* **URL**  

  /api/public/v1/p2p/profile

* **Method:**

  `POST`

* **URL Params**  

   None

* **Data Params**

  **Optional:**  
    `nickname=[string]` - P2P nickname  
    `tg_userid=[int]` - Telegram user id  

* **Success Response:**

```json
{
  "fullname": "John Doe",
  "nickname": "johndoe",
  "user_type": 2,
  "tg_userid": 10000000000,
  "requisites": [
    {
      "id": 12,      
      "requisites": "1111222233334444",
      "holder": "JOHN DOE",
      "payment_method": {
        "id": 3,
        "name": "Sepa",
        "logo": "https://example.com/upload/uploads/paymentmethods/logo/sepa.png",
        "fiat_currency": "EUR"
      }
    }
  ]
}
```

* **Response status codes**  

  `200` - OK
  
  `400` - Incorrect query params (details in response)


**Get fiat rates**  
----
  Returns fiat rates for chosen crypto currency.

* **URL**  

  /api/public/v1/p2p/rates

* **Method:**

  `GET`

* **URL Params**  

   **Required:**  
    `currency=[string]` - Crypto currency symbol

* **Data Params**

  None

* **Success Response:**

```json
{
  "prices": {
    "USD": "0.9991",
    "EUR": "0.94553706"
  },
  "p2p_prices": {
    "USD": "1.01",
    "EUR": "0.962"
  }
}

```

* **Response status codes**  

  `200` - OK
  
  `400` - Incorrect query params (details in response)


**Get available payment methods**  
----
  Returns available payment methods.

* **URL**  

  /api/public/v1/p2p/methods

* **Method:**

  `GET`

* **URL Params**  

   None

* **Data Params**

  None

* **Success Response:**

```json
[
  {
    "id": 3,
    "name": "SEPA",
    "logo": "https://example.com/upload/uploads/paymentmethods/logo/sepa_6LMaIWa.png",
    "fiat_currency": "EUR"
  }
]

```

* **Response status codes**  

  `200` - OK
  
  `400` - Incorrect query params (details in response)


**Get user requisites**  
----
  Returns current user requisites.

* **URL**  

  /api/public/v1/p2p/requisites

* **Method:**

  `GET`

* **URL Params**  

   None

* **Data Params**

  None

* **Success Response:**

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 12,
      "payment_method": {
        "id": 3,
        "name": "Sepa",
        "logo": "https://example.com/upload/uploads/paymentmethods/logo/social-en_CfqvhgQ.png",
        "fiat_currency": "EUR"
      },
      "requisites": "1111222233334444",
      "holder": "JOHN DOE"
    }
  ]
}
```

* **Response status codes**  

  `200` - OK
  
  `400` - Incorrect query params (details in response)

**Create user requisites**  
----
  Creates current user requisites.

* **URL**  

  /api/public/v1/p2p/requisites

* **Method:**

  `POST`

* **URL Params**  

   None

* **Data Params**

  **Required:**  
    `payment_method=[int]` - payment method ID  
    `requisites=[string]` - card number or anything like that  
    `holder=[string]` - card holder  

* **Success Response:**

```json
{
    "id": 12,
    "payment_method": {
      "id": 3,
      "name": "Sepa",
      "logo": "https://example.com/upload/uploads/paymentmethods/logo/social-en_CfqvhgQ.png",
      "fiat_currency": "EUR"
    },
    "requisites": "1111222233334444",
    "holder": "JOHN DOE"
}
```

* **Response status codes**  

  `201` - Created
  
  `400` - Incorrect query params (details in response)


**Change user requisites**  
----
  Changes current user requisites.

* **URL**  

  /api/public/v1/p2p/requisites/<requisites_id>

* **Method:**

  `PATCH`

* **URL Params**  

   None

* **Data Params**

  **Optional:**  
    `payment_method=[int]` - payment method ID  
    `requisites=[string]` - card number or anything like that  
    `holder=[string]` - card holder  

* **Success Response:**

```json
{
    "id": 12,
    "payment_method": {
      "id": 3,
      "name": "Sepa",
      "logo": "https://example.com/upload/uploads/paymentmethods/logo/social-en_CfqvhgQ.png",
      "fiat_currency": "EUR"
    },
    "requisites": "1111222233334444",
    "holder": "JOHN DOE"
}
```

* **Response status codes**  

  `200` - Ok
  
  `400` - Incorrect query params (details in response)


**Delete user requisites**  
----
  Deletes current user requisites.

* **URL**  

  /api/public/v1/p2p/requisites/<requisites_id>

* **Method:**

  `DELETE`

* **URL Params**  

   None

* **Data Params**

  None  

* **Success Response:**

```json
```

* **Response status codes**  

  `204` - Successfully deleted
  
  `400` - Incorrect query params (details in response)


# P2P Offers  

**Response params**  
----  

`operation` - 1 - Buy, 2 - Sell   
`state` - 1 - Opened, 2 - Cancelled, 3 - Hidden, 4 - Executed  
`price_type` - 1 - Fixed, 2 - External  

**Get user offers**  
----
  Returns current user offers.

* **URL**  

  /api/public/v1/p2p/offers

* **Method:**

  `GET`

* **URL Params**  

   None

* **Data Params**

  None

* **Success Response:**

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 116,
      "crypto_currency": "USDT",
      "fiat_currency": "EUR",
      "nickname": "test",
      "created": "1655371707",
      "updated": "1655377148",
      "state": 1,
      "operation": 2,
      "price_type": 1,
      "price": 0.99,
      "otc_percent": 0.0,
      "comment": "dfgdfg",
      "amount_total": 300,
      "amount_left": 100,
      "order_limit_min": 100.0,
      "order_limit_max": 150.0,
      "deal_lifetime": 15,
      "tg_userid": null,
      "requisites": [
        12
      ]
    }    
  ]
}
```

* **Response status codes**  

  `200` - OK
  
  `400` - Incorrect query params (details in response)


**Get offer details**  
----
  Returns current user offer by id.

* **URL**  

  /api/public/v1/p2p/offers/<offer_id>

* **Method:**

  `GET`

* **URL Params**  

   None

* **Data Params**

  None

* **Success Response:**

```json
{
  "id": 116,
  "crypto_currency": "USDT",
  "fiat_currency": "EUR",
  "nickname": "test",
  "created": "1655371707",
  "updated": "1655377148",
  "state": 1,
  "operation": 2,
  "price_type": 1,
  "price": 0.99,
  "otc_percent": 0.0,
  "comment": "dfgdfg",
  "amount_total": 300,
  "amount_left": 100,
  "order_limit_min": 100.0,
  "order_limit_max": 150.0,
  "deal_lifetime": 15,
  "tg_userid": null,
  "requisites": [
    12
  ]
}
```

* **Response status codes**  

  `200` - OK
  
  `400` - Incorrect query params (details in response)


**Create offer**  
----
  Creates new offer.

* **URL**  

  /api/public/v1/p2p/offers

* **Method:**

  `POST`

* **URL Params**  

   None

* **Data Params**

  **Required:**  
    `crypto_currency=[string]` - crypto currency  
    `fiat_currency=[string]` - fiat currency  
    `operation=[int]` - 1 - Buy, 2 - Sell  
    `price_type=[int]` - 1 -  Fixed, 2 - External  
    `price=[decimal]` - price if price_type is fixed  
    `otc_percent=[decimal]` - price deviation if price_type is external  
    `comment=[string]` - comment  
    `amount=[decimal]` - offer amount  
    `order_limit_min=[decimal]` - min deal amount in fiat  
    `order_limit_max=[decimal]` - max deal amount in fiat  
    `deal_lifetime=[string]` - deal lifetime in minutes  
    `tg_userid=[string]` - telegram user id   
    `requisites=[list of int]` - list of current user requisites IDs  

* **Success Response:**

```json
{
  "id": 116,
  "crypto_currency": "USDT",
  "fiat_currency": "EUR",
  "nickname": "test",
  "created": "1655371707",
  "updated": "1655377148",
  "state": 1,
  "operation": 2,
  "price_type": 1,
  "price": 0.99,
  "otc_percent": 0.0,
  "comment": "dfgdfg",
  "amount_total": 300,
  "amount_left": 100,
  "order_limit_min": 100.0,
  "order_limit_max": 150.0,
  "deal_lifetime": 15,
  "tg_userid": null,
  "requisites": [
    12
  ]
}
```

* **Response status codes**  

  `201` - Created
  
  `400` - Incorrect query params (details in response)


**Change offer**  
----
  Changes offer by id.

* **URL**  

  /api/public/v1/p2p/offers/<offer_id>

* **Method:**

  `PATCH`

* **URL Params**  

   None

* **Data Params**

  **Optional:**  
    `price_type=[int]` - 1 -  Fixed, 2 - External  
    `price=[decimal]` - price if price_type is fixed  
    `otc_percent=[decimal]` - price deviation if price_type is external    
    `comment=[string]` - comment  
    `amount_left=[decimal]` - new offer amount_left   
    `order_limit_min=[decimal]` - min deal amount in fiat  
    `order_limit_max=[decimal]` - max deal amount in fiat  
    `deal_lifetime=[string]` - deal lifetime in minutes   
    `tg_userid=[string]` - telegram user id   

* **Success Response:**

```json
{
  "id": 116,
  "crypto_currency": "USDT",
  "fiat_currency": "EUR",
  "nickname": "test",
  "created": "1655371707",
  "updated": "1655377148",
  "state": 1,
  "operation": 2,
  "price_type": 1,
  "price": 0.99,
  "otc_percent": 0.0,
  "comment": "dfgdfg",
  "amount_total": 300,
  "amount_left": 100,
  "order_limit_min": 100.0,
  "order_limit_max": 150.0,
  "deal_lifetime": 15,
  "tg_userid": null,
  "requisites": [
    12
  ]
}
```

* **Response status codes**  

  `200` - OK
  
  `400` - Incorrect query params (details in response)


**Cancel offer**  
----
  Cancel offer by id.

* **URL**  

  /api/public/v1/p2p/offers/<offer_id>

* **Method:**

  `DELETE`

* **URL Params**  

   None

* **Data Params**

  None

* **Success Response:**

```json
```

* **Response status codes**  

  `204` - Cancelled
  
  `400` - Incorrect query params (details in response)


**Hide offer**  
----
  Hides offer by id.

* **URL**  

  /api/public/v1/p2p/offers/<offer_id>/make_hidden

* **Method:**

  `POST`

* **URL Params**  

   None

* **Data Params**

  **Required**  
   `hidden=[bool]`

* **Success Response:**

```json
{
  "id": 116,
  "crypto_currency": "USDT",
  "fiat_currency": "EUR",
  "nickname": "test",
  "created": "1655371707",
  "updated": "1655377148",
  "state": 1,
  "operation": 2,
  "price_type": 1,
  "price": 0.99,
  "otc_percent": 0.0,
  "comment": "dfgdfg",
  "amount_total": 300,
  "amount_left": 100,
  "order_limit_min": 100.0,
  "order_limit_max": 150.0,
  "deal_lifetime": 15,
  "tg_userid": null,
  "requisites": [
    12
  ]
}
```

* **Response status codes**  

  `204` - Cancelled
  
  `400` - Incorrect query params (details in response)


# P2P Deals
**Response params**  
----  

`operation` - 1 - Buy, 2 - Sell   
`state` - 1 - Waiting for payment, 2 - Waiting for payment confirmation, 3 - Completed, 4 - Failed  

**Get user deals**  
----
  Returns user deals.

* **URL**  

  /api/public/v1/p2p/deals

* **Method:**

  `GET`

* **URL Params**  

   None

* **Data Params**

  None

* **Success Response:**

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 317,
      "created": "1656063757",
      "ends_at": "1656064657",
      "deal_lifetime": 15,
      "buyer": "test",
      "seller": "trade2",
      "crypto_currency": "USDT",
      "fiat_currency": "EUR",
      "operation": 1,
      "crypto_amount": 0.9,
      "fiat_amount": 48.825,
      "state": 4,
      "chat": 336,
      "cancelable": false,      
      "comment": "some comment",
      "is_merchant": false,
      "available_requisites": [
        {
          "id": 9,
          "payment_method": {
            "id": 1,
            "name": "Sepa",
            "logo": "https://example.com/upload/uploads/paymentmethods/logo/social-en_CfqvhgQ.png",
            "fiat_currency": "EUR"
          },
          "requisites": "9999888877776666",
          "holder": "trade one"
        },
        {
          "id": 23,
          "payment_method": {
            "id": 1,
            "name": "Sepa",
            "logo": "https://example.com/upload/uploads/paymentmethods/logo/social-en_CfqvhgQ.png",
            "fiat_currency": "USD"
          },
          "requisites": "1231123112311231",
          "holder": "asdas asdasd"
        }     
      ],
      "requisite": {
        "id": 9,
        "payment_method": {
          "id": 1,
          "name": "Sepa",
          "logo": "https://example.com/upload/uploads/paymentmethods/logo/social-en_CfqvhgQ.png",
          "fiat_currency": "EUR"
        },
        "requisites": "9999888877776666",
        "holder": "trade one"
      },      
    }    
  ]
}
```

* **Response status codes**  

  `200` - Ok
  
  `400` - Incorrect query params (details in response)


**Get user deal details**  
----
  Returns user deal by id.

* **URL**  

  /api/public/v1/p2p/deals/<deal_id>

* **Method:**

  `GET`

* **URL Params**  

   None

* **Data Params**

  None

* **Success Response:**

```json
{
  "id": 317,
  "created": "1656063757",
  "ends_at": "1656064657",
  "deal_lifetime": 15,
  "buyer": "test",
  "seller": "trade2",
  "crypto_currency": "USDT",
  "fiat_currency": "EUR",
  "operation": 1,
  "crypto_amount": 0.9,
  "fiat_amount": 48.825,
  "state": 4,
  "chat": 336,
  "cancelable": false,      
  "comment": "some comment",
  "is_merchant": false,
  "available_requisites": [
    {
      "id": 9,
      "payment_method": {
        "id": 1,
        "name": "Sepa",
        "logo": "https://example.com/upload/uploads/paymentmethods/logo/social-en_CfqvhgQ.png",
        "fiat_currency": "EUR"
      },
      "requisites": "9999888877776666",
      "holder": "trade one"
    },
    {
      "id": 23,
      "payment_method": {
        "id": 1,
        "name": "Sepa",
        "logo": "https://example.com/upload/uploads/paymentmethods/logo/social-en_CfqvhgQ.png",
        "fiat_currency": "USD"
      },
      "requisites": "1231123112311231",
      "holder": "asdas asdasd"
    }     
  ],
  "requisite": {
    "id": 9,
    "payment_method": {
      "id": 1,
      "name": "Sepa",
      "logo": "https://example.com/upload/uploads/paymentmethods/logo/social-en_CfqvhgQ.png",
      "fiat_currency": "EUR"
    },
    "requisites": "9999888877776666",
    "holder": "trade one"
  },      
}
```

* **Response status codes**  

  `200` - Ok
  
  `400` - Incorrect query params (details in response)


**Create new deal**  
----
  Creates new deal.

* **URL**  

  /api/public/v1/p2p/deals

* **Method:**

  `POST`

* **URL Params**  

   None

* **Data Params**

  **Required**  
    `offer=[int]` - Offer ID  
    `crypto_amount=[decimal]` - amount in crypto currency  
    `fiat_amount=[decimal]` - amount in fiat currency  

* **Success Response:**

```json
{
  "id": 317,
  "user": 1313,
  "offer": 111,
  "crypto_amount": 0.9,
  "fiat_amount": 48.825
}
```

* **Response status codes**  

  `201` - Ok
  
  `400` - Incorrect query params (details in response)


**Cancel deal**  
----
  Cancel user deal by id.

* **URL**  

  /api/public/v1/p2p/deals/<deal_id>/cancel

* **Method:**

  `POST`

* **URL Params**  

   None

* **Data Params**

  None

* **Success Response:**

```json
{
  "id": 317,
  "created": "1656063757",
  "ends_at": "1656064657",
  "deal_lifetime": 15,
  "buyer": "test",
  "seller": "trade2",
  "crypto_currency": "USDT",
  "fiat_currency": "EUR",
  "operation": 1,
  "crypto_amount": 0.9,
  "fiat_amount": 48.825,
  "state": 4,
  "chat": 336,
  "cancelable": false,      
  "comment": "some comment",
  "is_merchant": false,
  "available_requisites": [
    {
      "id": 9,
      "payment_method": {
        "id": 1,
        "name": "Sepa",
        "logo": "https://example.com/upload/uploads/paymentmethods/logo/social-en_CfqvhgQ.png",
        "fiat_currency": "EUR"
      },
      "requisites": "9999888877776666",
      "holder": "trade one"
    },
    {
      "id": 23,
      "payment_method": {
        "id": 1,
        "name": "Sepa",
        "logo": "https://example.com/upload/uploads/paymentmethods/logo/social-en_CfqvhgQ.png",
        "fiat_currency": "USD"
      },
      "requisites": "1231123112311231",
      "holder": "asdas asdasd"
    }     
  ],
  "requisite": {
    "id": 9,
    "payment_method": {
      "id": 1,
      "name": "Sepa",
      "logo": "https://example.com/upload/uploads/paymentmethods/logo/social-en_CfqvhgQ.png",
      "fiat_currency": "EUR"
    },
    "requisites": "9999888877776666",
    "holder": "trade one"
  },      
}
```

* **Response status codes**  

  `200` - Ok
  
  `400` - Incorrect query params (details in response)


**Make deal paid**  
----
  Make deal paid.

* **URL**  

  /api/public/v1/p2p/deals/<deal_id>/make_paid

* **Method:**

  `POST`

* **URL Params**  

   None

* **Data Params**
  
  **Required**  
   `requisite=[int]` - Requisite ID from "available_requisites" field

* **Success Response:**

```json
{
  "id": 317,
  "created": "1656063757",
  "ends_at": "1656064657",
  "deal_lifetime": 15,
  "buyer": "test",
  "seller": "trade2",
  "crypto_currency": "USDT",
  "fiat_currency": "EUR",
  "operation": 1,
  "crypto_amount": 0.9,
  "fiat_amount": 48.825,
  "state": 4,
  "chat": 336,
  "cancelable": false,      
  "comment": "some comment",
  "is_merchant": false,
  "available_requisites": [
    {
      "id": 9,
      "payment_method": {
        "id": 1,
        "name": "Sepa",
        "logo": "https://example.com/upload/uploads/paymentmethods/logo/social-en_CfqvhgQ.png",
        "fiat_currency": "EUR"
      },
      "requisites": "9999888877776666",
      "holder": "trade one"
    },
    {
      "id": 23,
      "payment_method": {
        "id": 1,
        "name": "Sepa",
        "logo": "https://example.com/upload/uploads/paymentmethods/logo/social-en_CfqvhgQ.png",
        "fiat_currency": "USD"
      },
      "requisites": "1231123112311231",
      "holder": "asdas asdasd"
    }     
  ],
  "requisite": {
    "id": 9,
    "payment_method": {
      "id": 1,
      "name": "Sepa",
      "logo": "https://example.com/upload/uploads/paymentmethods/logo/social-en_CfqvhgQ.png",
      "fiat_currency": "EUR"
    },
    "requisites": "9999888877776666",
    "holder": "trade one"
  },      
}
```

* **Response status codes**  

  `200` - Ok
  
  `400` - Incorrect query params (details in response)


**Confirm deal**  
----
  Confirm the deal.

* **URL**  

  /api/public/v1/p2p/deals/<deal_id>/confirm

* **Method:**

  `POST`

* **URL Params**  

   None

* **Data Params**
  
  None

* **Success Response:**

```json
{
  "id": 317,
  "created": "1656063757",
  "ends_at": "1656064657",
  "deal_lifetime": 15,
  "buyer": "test",
  "seller": "trade2",
  "crypto_currency": "USDT",
  "fiat_currency": "EUR",
  "operation": 1,
  "crypto_amount": 0.9,
  "fiat_amount": 48.825,
  "state": 4,
  "chat": 336,
  "cancelable": false,      
  "comment": "some comment",
  "is_merchant": false,
  "available_requisites": [
    {
      "id": 9,
      "payment_method": {
        "id": 1,
        "name": "Sepa",
        "logo": "https://example.com/upload/uploads/paymentmethods/logo/social-en_CfqvhgQ.png",
        "fiat_currency": "EUR"
      },
      "requisites": "9999888877776666",
      "holder": "trade one"
    },
    {
      "id": 23,
      "payment_method": {
        "id": 1,
        "name": "Sepa",
        "logo": "https://example.com/upload/uploads/paymentmethods/logo/social-en_CfqvhgQ.png",
        "fiat_currency": "USD"
      },
      "requisites": "1231123112311231",
      "holder": "asdas asdasd"
    }     
  ],
  "requisite": {
    "id": 9,
    "payment_method": {
      "id": 1,
      "name": "Sepa",
      "logo": "https://example.com/upload/uploads/paymentmethods/logo/social-en_CfqvhgQ.png",
      "fiat_currency": "EUR"
    },
    "requisites": "9999888877776666",
    "holder": "trade one"
  },      
}
```

* **Response status codes**  

  `200` - Ok
  
  `400` - Incorrect query params (details in response)


# Chat

**Response params**  
----

`message_type` - 1 - deal created, 2 - deal paid, 3 - deal completed, 4 - deal cancelled


**Get chat messages**  
----
  Returns messages of selected chat.

* **URL**  

  /api/public/v1/chat/messages/<chat_id>

* **Method:**

  `GET`

* **URL Params**  

   None

* **Data Params**
  
  None

* **Success Response:**

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 619,
      "user": "test@test.net",
      "user_id": 2457,
      "chat_id": 7,
      "attachments": [],
      "created": "1656086558",
      "text": "test message 1",
      "system_message": {}
    },
    {
      "id": 618,
      "user": "test1@test.net",
      "user_id": 2458,
      "chat_id": 7,
      "attachments": [],
      "created": "1656086485",
      "text": "test message 2",
      "system_message": {}
    }
  ]
}
```

* **Response status codes**  

  `200` - Ok
  
  `400` - Incorrect query params (details in response)


[comment]: <> (**Upload chat attachment**  )

[comment]: <> (----)

[comment]: <> (  Uploads documents to server)

[comment]: <> (* **URL**  )

[comment]: <> (  /api/public/v1/chat/upload)

[comment]: <> (* **Method:**)

[comment]: <> (  `POST`)

[comment]: <> (* **URL Params**  )

[comment]: <> (   None)

[comment]: <> (* **Data Params**)
  
[comment]: <> (  `file=[file multipart/form-data]`)

[comment]: <> (* **Success Response:**)

[comment]: <> (```json)

[comment]: <> ({)

[comment]: <> (  "status": true, )

[comment]: <> (  "data": {)

[comment]: <> (    "id": '<uuid>', )

[comment]: <> (    "link": "https://example.com/uploads/someimg.jpg")

[comment]: <> (  })

[comment]: <> (})

[comment]: <> (```)

[comment]: <> (* **Response status codes**  )

[comment]: <> (  `200` - Ok)
  
[comment]: <> (  `400` - Incorrect query params &#40;details in response&#41;)


**Write chat message**  
----
  Writes message to selected chat

* **URL**  

  /api/public/v1/chat/write

* **Method:**

  `POST`

* **URL Params**  

   None

* **Data Params**
  
  **Required**  
    `chat=[int]` - chat id  
    `text=[string]` - message text  

[comment]: <> (    `attachments=[list of uuid]` - list of attachments uuids  )
    
[comment]: <> (    "text" and "attachments" fields are optional, but message must contain at least one of them.)

* **Success Response:**

```json
{
  "id": 618,
  "user": "test1@test.net",
  "user_id": 2458,
  "chat_id": 7,
  "attachments": [],
  "created": "1656086485",
  "text": "test message 2",
  "system_message": {}
}
```

* **Response status codes**  

  `200` - Ok
  
  `400` - Incorrect query params (details in response)