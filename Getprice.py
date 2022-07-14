import requests
import json
from time import sleep
from requests.api import get
import  talib
import numpy as np
from binance.client import Client
from datetime import datetime
import psycopg2
from psycopg2 import Error

from config import API_KEY,API_SECRET

client = Client(api_key=API_KEY,api_secret=API_SECRET)

RSI_PERIOD = 1400
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

AUM = 1000 # Dolar bazında bütçe
ALLOCATION = 10 # Adet bazınca kaç adet farklı coin alacak.
AUM_OF_TRADE = AUM / ALLOCATION # Trade yapacagı bütçe

Buy_Rate = 0.5 # alış noktası
Sell_Rate = 0.5 # satış noktası
Panic_Sell = -0.9 # degisim eksi yonde ise panic sell
Tolerans = 0.3 
Profit_Sell = 0.9

Wallet = {}
Sell = {}
dict_symbol = {}



def get_price_list(type) -> tuple:
    try:
        all_prices = json.loads(requests.get('https://api.binance.com/api/v3/ticker/price').text) 
        type_of_prices = [price for price in all_prices if type in price['symbol'][-4:]]
        return type_of_prices        
    except:
        pass



def check_prices(symbols : tuple):
    global dict_symbol
    for symbol in symbols:
        if symbol["symbol"] in dict_symbol:
           dict_symbol[symbol["symbol"]].append(float(symbol["price"])) 
        else:
            dict_symbol[symbol["symbol"]] = []
            dict_symbol[symbol["symbol"]].append(float(symbol["price"]))

def check_symbos_for_buy():
    global dict_symbol
    buy_list = []
    for symbol in dict_symbol:
        np_closes = np.array(dict_symbol[symbol][-RSI_PERIOD:])
        diff = dict_symbol[symbol][0] - dict_symbol[symbol][-1]
        changes = diff / dict_symbol[symbol][0] * 100
        if changes != 0 :
            if changes >= Buy_Rate:
                buy_list.append(symbol)
    return buy_list


def lets_buy(buy_list):
    global dict_symbol,Wallet
    for symbol in buy_list:
        last_price = dict_symbol[symbol][-1]
        
        qty = AUM_OF_TRADE / last_price  
        # info = client.get_symbol_info(symbol)
        # test = client.create_test_order(symbol=symbol, side=client.SIDE_BUY, type=Client.ORDER_TYPE_MARKET,
        #                          quantity= float(round(qty, 2)))
        if symbol not in Wallet and len(Wallet) < ALLOCATION:
            Wallet[symbol] = {'price' : last_price, 'qty' : qty}



def moving_average(a, n=3) :
    ret = np.cumsum(a, dtype=float)
    ret[n:] = ret[n:] - ret[:-n]
    return ret[n - 1:] / n

def check_wallet(list_of_symbols):
    for symbol in list_of_symbols:
        current_price = float(symbol["price"])
        if Wallet.get(symbol['symbol']) != None:
            buy_price = Wallet[symbol['symbol']]['price']
            diff = current_price - buy_price 
            changes = diff / buy_price * 100

            """ lets check tolerans
                Bazen son fiyat düşmüş olsada genel ivme yukarı olabilir
                bu yüzden genele bakıp eğer fiyat yükselişte ise satmayalım.
            """
            # avg_price = sum(dict_symbol[symbol['symbol']][-20:]) / len(dict_symbol[symbol['symbol']][-20:])
            is_trend_positive = np.all(np.diff(moving_average(np.array(dict_symbol[symbol['symbol']]), n=200))>0)            
            # diff = current_price - avg_price 
            # changes_tolerans = diff / avg_price * 100            

            if changes >= Sell_Rate and changes != 0 : 
                if is_trend_positive:
                    continue               
                sell_aum = current_price * Wallet[symbol['symbol']]['qty'] 

                del Wallet[symbol['symbol']]
                # print('{} sold for {} $'.format(symbol['symbol'],sell_aum))
                if symbol["symbol"] in Sell:
                    Sell[symbol["symbol"]].append(sell_aum - AUM_OF_TRADE) 
                else:
                    Sell[symbol["symbol"]] = []             
                    Sell[symbol['symbol']].append(sell_aum - AUM_OF_TRADE)  
            elif changes <= Panic_Sell and is_trend_positive == False:
                sell_aum = current_price * Wallet[symbol['symbol']]['qty'] 
                del Wallet[symbol['symbol']]
                # print('{} sold for {} $'.format(symbol['symbol'],sell_aum))
                if symbol["symbol"] in Sell:
                    Sell[symbol["symbol"]].append(sell_aum - AUM_OF_TRADE) 
                else:
                    Sell[symbol["symbol"]] = []             
                    Sell[symbol['symbol']].append(sell_aum - AUM_OF_TRADE)                  


def get_aum():
    pass
    total_aum = 0
    for symbol in Sell:
        total_aum += sum([k for k in Sell[symbol]])
    
    print(AUM + round(total_aum,4))


def add_prices_to_db(list_of_symbols,source):
    try:
        host = "localhost"
        dbname = "postgres"
        user = "postgres"
        password = "1234"
        sslmode = "require"

        conn_string = "host={0} user={1} dbname={2} password={3} ".format(host, user, dbname, password)        
        conn = psycopg2.connect(conn_string)
        conn.autocommit = True
        cur = conn.cursor()
        
        for symbol in list_of_symbols:
            cur.execute("""INSERT INTO public.cb_price_log
                        (createdate, price, "source", currency)
                        VALUES('{}', {}, '{}', '{}');
                        """.format(datetime.now(),float(symbol["price"]),source,symbol["symbol"]))
            
    except (Exception, Error)  as e :
        print(e)

if __name__== '__main__':
    while True:
        sleep(0.5)
        list_of_symbols = get_price_list('USDT')
        # add_prices_to_db(list_of_symbols,"https://api.binance.com/api/v3/ticker/price") # Bkz TODO.No:1
        if list_of_symbols != None:
            check_wallet(list_of_symbols)
            check_prices(list_of_symbols)
            buy_list = check_symbos_for_buy()
            if buy_list != []:
                lets_buy(buy_list)
            get_aum()

# TODO.No:1
"""
Fiyatları db ye kaydetmek isterseniz tablo DDL i 
Postgres Sql

CREATE TABLE public.cb_price_log (
	id int4 NOT NULL GENERATED ALWAYS AS IDENTITY,
	createdate timestamp NOT NULL,
	price numeric(20, 8) NOT NULL,
	"source" varchar NULL,
	currency varchar NULL
);
CREATE UNIQUE INDEX cb_price_log_id_idx ON public.cb_price_log USING btree (id);


"""