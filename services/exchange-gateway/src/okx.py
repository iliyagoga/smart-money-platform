import base64,hashlib,hmac,json
from datetime import datetime,timezone
from urllib.parse import urlencode

TIMEFRAMES={"M1":"1m","M5":"5m","M15":"15m","H1":"1H","H4":"4H","D1":"1D"}
REVERSE_TIMEFRAMES={v:k for k,v in TIMEFRAMES.items()}

def timestamp(): return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z")
def signature(secret,stamp,method,path,body=""):
    raw=f"{stamp}{method.upper()}{path}{body}".encode()
    return base64.b64encode(hmac.new(secret.encode(),raw,hashlib.sha256).digest()).decode()
def auth_headers(key,secret,passphrase,method,path,body="",demo=True,stamp=None):
    stamp=stamp or timestamp(); result={"OK-ACCESS-KEY":key,"OK-ACCESS-SIGN":signature(secret,stamp,method,path,body),"OK-ACCESS-TIMESTAMP":stamp,"OK-ACCESS-PASSPHRASE":passphrase,"Content-Type":"application/json"}
    if demo: result["x-simulated-trading"]="1"
    return result
def candle(item,symbol,timeframe):
    return {"symbol":symbol,"timeframe":timeframe,"timestamp":int(item[0]),"open":float(item[1]),"high":float(item[2]),"low":float(item[3]),"close":float(item[4]),"volume":float(item[5]),"is_closed":item[8]=="1"}
def trade(item):
    return {"symbol":item["instId"],"trade_id":item["tradeId"],"timestamp":int(item["ts"]),"price":float(item["px"]),"volume":float(item["sz"]),"side":item["side"].lower()}
def book(item,symbol):
    return {"symbol":symbol,"timestamp":int(item["ts"]),"sequence_id":int(item.get("seqId",0)),"bids":[[float(x[0]),float(x[1])] for x in item["bids"]],"asks":[[float(x[0]),float(x[1])] for x in item["asks"]]}
