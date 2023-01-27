# Common reponse status codes

  `429` - Too many requests per second. Max 2 requests per second. 


# Endpoints
**Overview**
----
  Overview of market data for all tickers.

* **URL**  

  /api/external/coingecko/pairs

* **Method:**  

  `GET`
  
* **URL Params**  

  None

* **Success Response:**  
```json
[
  {
    "ticker_id": "BTC_USDT",
    "base": "BTC",
    "target": "USDT"
  }
,
    ...
]
```

* **Response status codes**  

  `200` - OK


**Tickers**  
----

  24-hour rolling window price change statistics for all markets.

* **URL**  

  /api/external/coingecko/tickers

* **Method:**  

  `GET`
  
* **URL Params**  

  None

* **Success Response:**  

```json
[
    {
        "ticker_id": "BTC_USDT",
        "base_currency": "BTC",
        "target_currency": "USDT",
        "last_price": 39264.81878744,
        "base_volume": 33.65054155,
        "target_volume": 1299599.177102574,
        "ask": 39689.1014,
        "bid": 38903.1786,
        "high": 39711.17541238,
        "low": 37368.06659806
    },
    {
        "ticker_id": "ETH_USDT",
        "base_currency": "ETH",
        "target_currency": "USDT",
        "last_price": 1647.74866303,
        "base_volume": 136.82493965,
        "target_volume": 218573.03940451317,
        "ask": 1664.5608,
        "bid": 1631.5992,
        "high": 1655.25090624,
        "low": 1499.71974143
    }
]
```

* **Response status codes**  

  `200` - OK


**Order book**  
----

  Returns the order book of a specified market.

* **URL**  

  /api/external/coingecko/orderbook

* **Method:**  

  `GET`
  
* **URL Params**  

    **Required**  
    `ticker_id=[string]`

    **Optional:**  
    `depth=[integer]` - number of entries. 100 by default, max. 500

* **Success Response:**  

```json 
{
    "ticker_id": "BTC_USDT",
    "timestamp": 1606214465899,
    "asks": [
        [
            35000.359,
            0.5
        ],
        [
            36000.918,
            0.43692707
        ],
        [
            37000.996,
            0.16387891
        ]
    ],
    "bids": [
        [
            33000.32,
            0.5
        ],
        [
            34000.761,
            0.34773752
        ],
        [
            34999.683,
            0.005
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

  /api/external/coingecko/historical_trades

* **Method:**  

  `GET`
  
* **URL Params**  

  None

* **Data Params**

  None

* **Success Response:**  

```json 
{
    "buy": [
        {
            "trade_id": 60427931,
            "price": 1640.00181649,
            "base_volume": 0.06417397,
            "target_volume": 105.24542737137476,
            "trade_timestamp": 1612776266,
            "type": "buy"
        },
        {
            "trade_id": 60427922,
            "price": 1638.29187834,
            "base_volume": 0.08365746,
            "target_volume": 137.0553372805534,
            "trade_timestamp": 1612776206,
            "type": "buy"
        }
    "sell": [
        {
            "trade_id": 60427966,
            "price": 1640.00181649,
            "base_volume": 0.06417397,
            "target_volume": 105.24542737137476,
            "trade_timestamp": 1612776266,
            "type": "sell"
        },
        {
            "trade_id": 60427977,
            "price": 1638.29187834,
            "base_volume": 0.08365746,
            "target_volume": 137.0553372805534,
            "trade_timestamp": 1612776206,
            "type": "sell"
        }
    ]
}
```

* **Response status codes**  

  `200` - OK
