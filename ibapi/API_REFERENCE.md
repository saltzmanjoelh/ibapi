## IBKR TWS API Python (`ibapi`) — API Reference (Request/Callback Docs)

This repository is a Python implementation of the Interactive Brokers **TWS API** client library (`ibapi`). The TWS API is an **event-driven** socket protocol: you call **request methods** on `EClient`, and IB Gateway / TWS replies asynchronously by invoking **callback methods** on your `EWrapper` subclass.

- **Primary upstream docs**: [`https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/`](https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/)
- **Source of truth in this repo**:
  - `ibapi/client.py` (`EClient`: outbound requests)
  - `ibapi/wrapper.py` (`EWrapper`: inbound callbacks)
  - `tests/manual.py` (minimal runnable example wiring `EClient` + `EWrapper`)

### Table of contents

- [Quickstart (mental model)](#quickstart-mental-model)
- [Minimal skeleton (how to wire it)](#minimal-skeleton-how-to-wire-it)
- [API reference: Requests → Callbacks (+ End markers) + example payloads](#api-reference-requests--callbacks--end-markers--example-payloads)
  - [Connectivity / session lifecycle](#connectivity--session-lifecycle)
  - [Contract discovery / security definition](#contract-discovery--security-definition)
  - [Market data (L1 “watchlist” market data)](#market-data-l1-watchlist-market-data)
  - [Tick-by-tick market data](#tick-by-tick-market-data)
  - [Historical market data](#historical-market-data)
  - [Orders](#orders)
  - [Account / portfolio](#account--portfolio)
  - [Scanner](#scanner)
  - [News](#news)
  - [“End markers” cheat sheet](#end-markers-cheat-sheet)
- [Full method inventory (generated from source)](#full-method-inventory-generated-from-source)
  - [`EClient` (requests you can call)](#eclient-requests-you-can-call)
  - [`EWrapper` (callbacks IB calls on you)](#ewrapper-callbacks-ib-calls-on-you)
- [Legacy / installation notes (older)](#legacy--installation-notes-older)

### Quickstart (mental model)

- **You call**: `EClient.reqMatchingSymbols(reqId, pattern)`
- **IB calls you back**: `EWrapper.symbolSamples(reqId, contractDescriptions)`

Many requests have an explicit **completion callback** ending in `End`, e.g.:

- **You call**: `EClient.reqContractDetails(reqId, contract)`
- **IB calls**: `EWrapper.contractDetails(reqId, contractDetails)` (0..N times)
- **Then completes**: `EWrapper.contractDetailsEnd(reqId)` (exactly once)

### Minimal skeleton (how to wire it)

```python
from ibapi.client import EClient
from ibapi.wrapper import EWrapper

class App(EWrapper, EClient):
    def __init__(self):
        EWrapper.__init__(self)
        EClient.__init__(self, wrapper=self)

    # implement callbacks you care about, e.g.:
    # def symbolSamples(self, reqId, contractDescriptions): ...

app = App()
app.connect("127.0.0.1", 7497, clientId=0)  # port depends on TWS/IBG config
app.run()  # starts processing inbound messages & invoking callbacks
```

### API reference: Requests → Callbacks (+ End markers) + example payloads

Below, “Request” means an `EClient` method you call. “Callbacks” means `EWrapper` methods that may be invoked in response.

#### Connectivity / session lifecycle

- **Request**: `EClient.connect(host, port, clientId)`
  - **Callbacks (typical during handshake)**:
    - `EWrapper.connectAck()`
    - `EWrapper.managedAccounts(accountsList)`
    - `EWrapper.nextValidId(orderId)` (often used as “ready” signal for placing orders)
    - `EWrapper.currentTime(time)` / `EWrapper.currentTimeInMillis(timeInMillis)` (depends on host/version/requests)
    - `EWrapper.error(reqId, errorTime, errorCode, errorString, advancedOrderRejectJson)` (informational codes like 2104/2106/2158 are common)
- **Request**: `EClient.disconnect()`
  - **Callbacks**: `EWrapper.connectionClosed()`

Example (handshake-ish `error` notifications you’ll commonly see):

```text
ERROR -1 <ts> 2104 Market data farm connection is OK:usfarm
ERROR -1 <ts> 2106 HMDS data farm connection is OK:ushmds
ERROR -1 <ts> 2158 Sec-def data farm connection is OK:secdefil
```

#### Contract discovery / security definition

- **Request**: `EClient.reqMatchingSymbols(reqId, pattern)`
  - **Callbacks**:
    - `EWrapper.symbolSamples(reqId, contractDescriptions)`
  - **Example callback payload (shape)**:

```python
# symbolSamples(reqId=12001, contractDescriptions=[...])
[
  {
    "contract": {"conId": 265598, "symbol": "AAPL", "secType": "STK", "primaryExchange": "NASDAQ", "currency": "USD"},
    "derivativeSecTypes": ["OPT", "FOP", "WAR"]
  },
  # ...
]
```

- **Request**: `EClient.reqContractDetails(reqId, contract)`
  - **Callbacks**:
    - `EWrapper.contractDetails(reqId, contractDetails)` (0..N)
    - `EWrapper.bondContractDetails(reqId, contractDetails)` (bonds)
    - **End**: `EWrapper.contractDetailsEnd(reqId)`
  - **Example callback payload (shape)**:

```python
# contractDetails(reqId=3001, contractDetails=ContractDetails(...))
{
  "contract": {"conId": 265598, "symbol": "AAPL", "secType": "STK", "exchange": "SMART", "primaryExchange": "ISLAND", "currency": "USD"},
  "marketName": "NMS",
  "minTick": 0.01,
  "timeZoneId": "US/Eastern",
  "tradingHours": "20251015:0400-20251015:2000;...",
  "liquidHours": "20251015:0930-20251015:1600;..."
}
```

- **Request**: `EClient.reqSecDefOptParams(reqId, underlyingSymbol, futFopExchange, underlyingSecType, underlyingConId)`
  - **Callbacks**:
    - `EWrapper.securityDefinitionOptionParameter(reqId, exchange, underlyingConId, tradingClass, multiplier, expirations, strikes)` (0..N; often per exchange)
    - **End**: `EWrapper.securityDefinitionOptionParameterEnd(reqId)`

#### Market data (L1 “watchlist” market data)

- **Request**: `EClient.reqMktData(reqId, contract, genericTickList, snapshot, regulatorySnapshot, mktDataOptions)`
  - **Callbacks (common)**:
    - `EWrapper.tickPrice(reqId, tickType, price, attrib)`
    - `EWrapper.tickSize(reqId, tickType, size)`
    - `EWrapper.tickString(reqId, tickType, value)`
    - `EWrapper.tickGeneric(reqId, tickType, value)`
    - `EWrapper.tickOptionComputation(reqId, tickType, tickAttrib, impliedVol, delta, optPrice, pvDividend, gamma, vega, theta, undPrice)` (options)
    - `EWrapper.tickReqParams(tickerId, minTick, bboExchange, snapshotPermissions)`
    - `EWrapper.marketDataType(reqId, marketDataType)` (after you call `reqMarketDataType(...)` or for delayed/frozen modes)
    - **Snapshot completion**: `EWrapper.tickSnapshotEnd(reqId)` (when `snapshot=True`)
    - **If requesting news ticks**: `EWrapper.tickNews(...)`
  - **Example tick stream (shape)**:

```text
tickPrice(reqId=1001, tickType=BID, price=276.17, attrib={canAutoExecute: True, pastLimit: False, preOpen: False})
tickSize(reqId=1001, tickType=BID_SIZE, size=900)
tickPrice(reqId=1001, tickType=ASK, price=276.20, attrib={...})
tickSize(reqId=1001, tickType=ASK_SIZE, size=300)
```

- **Request**: `EClient.cancelMktData(reqId)`
  - **Callbacks**: (none; ticks stop)

#### Tick-by-tick market data

- **Request**: `EClient.reqTickByTickData(reqId, contract, tickType, numberOfTicks, ignoreSize)`
  - **Callbacks (depends on `tickType`)**:
    - `EWrapper.tickByTickAllLast(reqId, tickType, time, price, size, tickAttribLast, exchange, specialConditions)`
    - `EWrapper.tickByTickBidAsk(reqId, time, bidPrice, askPrice, bidSize, askSize, tickAttribBidAsk)`
    - `EWrapper.tickByTickMidPoint(reqId, time, midPoint)`
  - **Note**: If `numberOfTicks > 0`, you may first receive one of the historical tick callbacks:
    - `EWrapper.historicalTicks(...)` / `historicalTicksBidAsk(...)` / `historicalTicksLast(...)`

#### Historical market data

- **Request**: `EClient.reqHistoricalData(reqId, contract, endDateTime, durationStr, barSizeSetting, whatToShow, useRTH, formatDate, keepUpToDate, chartOptions)`
  - **Callbacks**:
    - `EWrapper.historicalData(reqId, bar)` (0..N)
    - **End**: `EWrapper.historicalDataEnd(reqId, start, end)`
    - If `keepUpToDate=True`: `EWrapper.historicalDataUpdate(reqId, bar)` (streaming updates)

- **Request**: `EClient.reqHeadTimeStamp(reqId, contract, whatToShow, useRTH, formatDate)`
  - **Callbacks**: `EWrapper.headTimestamp(reqId, headTimestamp)`

- **Request**: `EClient.reqHistoricalTicks(reqId, contract, startDateTime, endDateTime, numberOfTicks, whatToShow, useRth, ignoreSize, miscOptions)`
  - **Callbacks (depends on `whatToShow`)**:
    - `EWrapper.historicalTicks(reqId, ticks, done)` (MIDPOINT)
    - `EWrapper.historicalTicksBidAsk(reqId, ticks, done)` (BID_ASK)
    - `EWrapper.historicalTicksLast(reqId, ticks, done)` (TRADES)

#### Orders

- **Request**: `EClient.placeOrder(orderId, contract, order)`
  - **Callbacks**:
    - `EWrapper.openOrder(orderId, contract, order, orderState)`
    - `EWrapper.orderStatus(orderId, status, filled, remaining, avgFillPrice, permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice)`
    - `EWrapper.execDetails(reqId, contract, execution)` (fills)
    - `EWrapper.commissionAndFeesReport(commissionAndFeesReport)` (fills)
    - Errors: `EWrapper.error(...)`

Example order status (shape):

```python
{
  "orderId": 347,
  "status": "PreSubmitted",
  "filled": "0",
  "remaining": "100",
  "avgFillPrice": 0.0,
  "permId": 979867961,
  "parentId": 0,
  "lastFillPrice": 0.0,
  "clientId": 0,
  "whyHeld": "",
  "mktCapPrice": 0.0
}
```

- **Request**: `EClient.cancelOrder(orderId, orderCancel)`
  - **Callbacks**: `EWrapper.orderStatus(...)` (state transitions), plus `EWrapper.error(...)` on issues

- **Request**: `EClient.reqOpenOrders()` / `EClient.reqAllOpenOrders()`
  - **Callbacks**:
    - `EWrapper.openOrder(...)` (0..N)
    - `EWrapper.orderStatus(...)` (0..N)
    - **End**: `EWrapper.openOrderEnd()`

- **Request**: `EClient.reqCompletedOrders(apiOnly)`
  - **Callbacks**:
    - `EWrapper.completedOrder(contract, order, orderState)` (0..N)
    - **End**: `EWrapper.completedOrdersEnd()`

#### Account / portfolio

- **Request**: `EClient.reqAccountSummary(reqId, groupName, tags)`
  - **Callbacks**:
    - `EWrapper.accountSummary(reqId, account, tag, value, currency)` (0..N)
    - **End**: `EWrapper.accountSummaryEnd(reqId)`
  - **Example callback payload (shape)**:

```text
accountSummary(reqId=2, account="DU1234567", tag="NetLiquidation", value="221425500.56", currency="USD")
accountSummaryEnd(reqId=2)
```

- **Request**: `EClient.reqAccountUpdates(subscribe, acctCode)`
  - **Callbacks**:
    - `EWrapper.updateAccountValue(key, val, currency, accountName)`
    - `EWrapper.updatePortfolio(contract, position, marketPrice, marketValue, averageCost, unrealizedPNL, realizedPNL, accountName)`
    - `EWrapper.updateAccountTime(timeStamp)`
    - **End**: `EWrapper.accountDownloadEnd(accountName)`

- **Request**: `EClient.reqPositions()`
  - **Callbacks**:
    - `EWrapper.position(account, contract, position, avgCost)` (0..N)
    - **End**: `EWrapper.positionEnd()`

#### Scanner

- **Request**: `EClient.reqScannerParameters()`
  - **Callbacks**: `EWrapper.scannerParameters(xml)`

- **Request**: `EClient.reqScannerSubscription(reqId, subscription, scannerSubscriptionOptions, scannerSubscriptionFilterOptions)`
  - **Callbacks**:
    - `EWrapper.scannerData(reqId, rank, contractDetails, distance, benchmark, projection, legsStr)` (0..N)
    - **End**: `EWrapper.scannerDataEnd(reqId)`

#### News

- **Request**: `EClient.reqNewsProviders()`
  - **Callbacks**: `EWrapper.newsProviders(newsProviders)`

- **Request**: `EClient.reqNewsArticle(reqId, providerCode, articleId, newsArticleOptions)`
  - **Callbacks**: `EWrapper.newsArticle(requestId, articleType, articleText)`

- **Request**: `EClient.reqHistoricalNews(reqId, conId, providerCodes, startDateTime, endDateTime, totalResults, historicalNewsOptions)`
  - **Callbacks**:
    - `EWrapper.historicalNews(requestId, time, providerCode, articleId, headline)` (0..N)
    - **End**: `EWrapper.historicalNewsEnd(requestId, hasMore)`

#### “End markers” cheat sheet

These callbacks commonly appear as “done”/completion markers for list-like requests:

- `reqContractDetails(...)` → `contractDetailsEnd(reqId)`
- `reqExecutions(...)` → `execDetailsEnd(reqId)`
- `reqOpenOrders()` / `reqAllOpenOrders()` → `openOrderEnd()`
- `reqPositions()` → `positionEnd()`
- `reqAccountSummary(...)` → `accountSummaryEnd(reqId)`
- `reqScannerSubscription(...)` → `scannerDataEnd(reqId)`
- `reqHistoricalData(...)` → `historicalDataEnd(reqId, start, end)`
- `reqSecDefOptParams(...)` → `securityDefinitionOptionParameterEnd(reqId)`
- `reqCompletedOrders(...)` → `completedOrdersEnd()`

And the raw end callbacks themselves:

- `contractDetailsEnd(reqId)`
- `execDetailsEnd(reqId)`
- `openOrderEnd()`
- `positionEnd()`
- `accountSummaryEnd(reqId)`
- `scannerDataEnd(reqId)`
- `historicalDataEnd(reqId, start, end)`
- `securityDefinitionOptionParameterEnd(reqId)`
- `completedOrdersEnd()`

### Full method inventory (generated from source)

This section exists to satisfy “list the methods that can be called” and “list the callbacks that are called” **directly from this repository’s source**.

#### `EClient` (requests you can call)

**Non-Protobuf methods**

```text
reset(self)
setConnState(self, connState)
sendMsg(self, msgId, msg)
logRequest(self, fnName, fnParams)
validateInvalidSymbols(self, host)
checkConnected(self)
startApi(self)
connect(self, host, port, clientId)
disconnect(self)
isConnected(self)
keyboardInterrupt(self)
keyboardInterruptHard(self)
setConnectOptions(self, opts)
setOptionalCapabilities(self, optCapab)
msgLoopTmo(self)
msgLoopRec(self)
run(self)
reqCurrentTime(self)
serverVersion(self)
setServerLogLevel(self, logLevel)
twsConnectionTime(self)
reqMktData(self, reqId, contract, genericTickList, snapshot, regulatorySnapshot, mktDataOptions)
cancelMktData(self, reqId)
reqMarketDataType(self, marketDataType)
reqSmartComponents(self, reqId, bboExchange)
reqMarketRule(self, marketRuleId)
reqTickByTickData(self, reqId, contract, tickType, numberOfTicks, ignoreSize)
cancelTickByTickData(self, reqId)
calculateImpliedVolatility(self, reqId, contract, optionPrice, underPrice, implVolOptions)
cancelCalculateImpliedVolatility(self, reqId)
calculateOptionPrice(self, reqId, contract, volatility, underPrice, optPrcOptions)
cancelCalculateOptionPrice(self, reqId)
exerciseOptions(self, reqId, contract, exerciseAction, exerciseQuantity, account, override, manualOrderTime, customerAccount, professionalCustomer)
placeOrder(self, orderId, contract, order)
validateOrderParameters(self, order)
validateAttachedOrdersParameters(self, attachedOrders)
cancelOrder(self, orderId, orderCancel)
reqOpenOrders(self)
reqAutoOpenOrders(self, bAutoBind)
reqAllOpenOrders(self)
reqGlobalCancel(self, orderCancel)
reqIds(self, numIds)
reqAccountUpdates(self, subscribe, acctCode)
reqAccountSummary(self, reqId, groupName, tags)
cancelAccountSummary(self, reqId)
reqPositions(self)
cancelPositions(self)
reqPositionsMulti(self, reqId, account, modelCode)
cancelPositionsMulti(self, reqId)
reqAccountUpdatesMulti(self, reqId, account, modelCode, ledgerAndNLV)
cancelAccountUpdatesMulti(self, reqId)
reqPnL(self, reqId, account, modelCode)
cancelPnL(self, reqId)
reqPnLSingle(self, reqId, account, modelCode, conid)
cancelPnLSingle(self, reqId)
reqExecutions(self, reqId, execFilter)
reqContractDetails(self, reqId, contract)
reqMktDepthExchanges(self)
reqMktDepth(self, reqId, contract, numRows, isSmartDepth, mktDepthOptions)
cancelMktDepth(self, reqId, isSmartDepth)
reqNewsBulletins(self, allMsgs)
cancelNewsBulletins(self)
reqManagedAccts(self)
requestFA(self, faData)
replaceFA(self, reqId, faData, cxml)
reqHistoricalData(self, reqId, contract, endDateTime, durationStr, barSizeSetting, whatToShow, useRTH, formatDate, keepUpToDate, chartOptions)
cancelHistoricalData(self, reqId)
reqHeadTimeStamp(self, reqId, contract, whatToShow, useRTH, formatDate)
cancelHeadTimeStamp(self, reqId)
reqHistogramData(self, tickerId, contract, useRTH, timePeriod)
cancelHistogramData(self, tickerId)
reqHistoricalTicks(self, reqId, contract, startDateTime, endDateTime, numberOfTicks, whatToShow, useRth, ignoreSize, miscOptions)
reqScannerParameters(self)
reqScannerSubscription(self, reqId, subscription, scannerSubscriptionOptions, scannerSubscriptionFilterOptions)
cancelScannerSubscription(self, reqId)
reqRealTimeBars(self, reqId, contract, barSize, whatToShow, useRTH, realTimeBarsOptions)
cancelRealTimeBars(self, reqId)
reqFundamentalData(self, reqId, contract, reportType, fundamentalDataOptions)
cancelFundamentalData(self, reqId)
reqNewsProviders(self)
reqNewsArticle(self, reqId, providerCode, articleId, newsArticleOptions)
reqHistoricalNews(self, reqId, conId, providerCodes, startDateTime, endDateTime, totalResults, historicalNewsOptions)
queryDisplayGroups(self, reqId)
subscribeToGroupEvents(self, reqId, groupId)
updateDisplayGroup(self, reqId, contractInfo)
unsubscribeFromGroupEvents(self, reqId)
verifyRequest(self, apiName, apiVersion)
verifyMessage(self, apiData)
verifyAndAuthRequest(self, apiName, apiVersion, opaqueIsvKey)
verifyAndAuthMessage(self, apiData, xyzResponse)
reqSecDefOptParams(self, reqId, underlyingSymbol, futFopExchange, underlyingSecType, underlyingConId)
reqSoftDollarTiers(self, reqId)
reqFamilyCodes(self)
reqMatchingSymbols(self, reqId, pattern)
reqCompletedOrders(self, apiOnly)
reqWshMetaData(self, reqId)
cancelWshMetaData(self, reqId)
reqWshEventData(self, reqId, wshEventData)
cancelWshEventData(self, reqId)
reqUserInfo(self, reqId)
reqCurrentTimeInMillis(self)
cancelContractData(self, reqId)
cancelHistoricalTicks(self, reqId)
```

**Protobuf variants (advanced)**

```text
sendMsgProtoBuf(self, msgId, msg)
useProtoBuf(self, msgId)
startApiProtoBuf(self, startApiRequestProto)
reqCurrentTimeProtoBuf(self, currentTimeRequestProto)
setServerLogLevelProtoBuf(self, setServerLogLevelRequestProto)
reqMarketDataProtoBuf(self, marketDataRequestProto)
cancelMarketDataProtoBuf(self, cancelMarketDataProto)
reqMarketDataTypeProtoBuf(self, marketDataTypeRequestProto)
reqSmartComponentsProtoBuf(self, smartComponentsRequestProto)
reqMarketRuleProtoBuf(self, marketRuleRequestProto)
reqTickByTickDataProtoBuf(self, tickByTickRequestProto)
cancelTickByTickProtoBuf(self, cancelTickByTickProto)
calculateImpliedVolatilityProtoBuf(self, calculateImpliedVolatilityRequestProto)
cancelCalculateImpliedVolatilityProtoBuf(self, cancelCalculateImpliedVolatilityProto)
calculateOptionPriceProtoBuf(self, calculateOptionPriceRequestProto)
cancelCalculateOptionPriceProtoBuf(self, cancelCalculateOptionPriceProto)
exerciseOptionsProtoBuf(self, exerciseOptionsRequestProto)
placeOrderProtoBuf(self, placeOrderRequestProto)
cancelOrderProtoBuf(self, cancelOrderRequestProto)
reqOpenOrdersProtoBuf(self, openOrdersRequestProto)
reqAutoOpenOrdersProtoBuf(self, autoOpenOrdersRequestProto)
reqAllOpenOrdersProtoBuf(self, allOpenOrdersRequestProto)
reqGlobalCancelProtoBuf(self, globalCancelRequestProto)
reqIdsProtoBuf(self, idsRequestProto)
reqAccountUpdatesProtoBuf(self, accountDataRequestProto)
reqAccountSummaryProtoBuf(self, accountSummaryRequestProto)
cancelAccountSummaryProtoBuf(self, cancelAccountSummaryProto)
reqPositionsProtoBuf(self, positionsRequestProto)
cancelPositionsProtoBuf(self, cancelPositionsProto)
reqPositionsMultiProtoBuf(self, positionsMultiRequestProto)
cancelPositionsMultiProtoBuf(self, cancelPositionsMultiProto)
reqAccountUpdatesMultiProtoBuf(self, accountUpdatesMultiRequestProto)
cancelAccountUpdatesMultiProtoBuf(self, cancelAccountUpdatesMultiProto)
reqPnLProtoBuf(self, pnlRequestProto)
cancelPnLProtoBuf(self, cancelPnLProto)
reqPnLSingleProtoBuf(self, pnlSingleRequestProto)
cancelPnLSingleProtoBuf(self, cancelPnLSingleProto)
reqExecutionsProtoBuf(self, executionRequestProto)
reqContractDataProtoBuf(self, contractDataRequestProto)
reqMarketDepthExchangesProtoBuf(self, marketDepthExchangesRequestProto)
reqMarketDepthProtoBuf(self, marketDepthRequestProto)
cancelMarketDepthProtoBuf(self, cancelMarketDepthProto)
reqNewsBulletinsProtoBuf(self, newsBulletinsRequestProto)
cancelNewsBulletinsProtoBuf(self, cancelNewsBulletinsProto)
reqManagedAcctsProtoBuf(self, managedAccountsRequestProto)
reqFAProtoBuf(self, faRequestProto)
replaceFAProtoBuf(self, faReplaceProto)
reqHistoricalDataProtoBuf(self, historicalDataRequestProto)
cancelHistoricalDataProtoBuf(self, cancelHistoricalDataProto)
reqHeadTimestampProtoBuf(self, headTimestampRequestProto)
cancelHeadTimestampProtoBuf(self, cancelHeadTimestampProto)
reqHistogramDataProtoBuf(self, histogramDataRequestProto)
cancelHistogramDataProtoBuf(self, cancelHistogramDataProto)
reqHistoricalTicksProtoBuf(self, historicalTicksRequestProto)
reqScannerParametersProtoBuf(self, scannerParametersRequestProto)
reqScannerSubscriptionProtoBuf(self, scannerSubscriptionRequestProto)
cancelScannerSubscriptionProtoBuf(self, cancelScannerSubscriptionProto)
reqRealTimeBarsProtoBuf(self, realTimeBarsRequestProto)
cancelRealTimeBarsProtoBuf(self, cancelRealTimeBarsProto)
reqFundamentalsDataProtoBuf(self, fundamentalsDataRequestProto)
cancelFundamentalsDataProtoBuf(self, cancelFundamentalsDataProto)
reqNewsProvidersProtoBuf(self, newsProvidersRequestProto)
reqNewsArticleProtoBuf(self, newsArticleRequestProto)
reqHistoricalNewsProtoBuf(self, historicalNewsRequestProto)
queryDisplayGroupsProtoBuf(self, queryDisplayGroupsRequestProto)
subscribeToGroupEventsProtoBuf(self, subscribeToGroupEventsRequestProto)
updateDisplayGroupProtoBuf(self, updateDisplayGroupRequestProto)
unsubscribeFromGroupEventsProtoBuf(self, unsubscribeFromGroupEventsRequestProto)
verifyRequestProtoBuf(self, verifyRequestProto)
verifyMessageProtoBuf(self, verifyMessageRequestProto)
reqSecDefOptParamsProtoBuf(self, secDefOptParamsRequestProto)
reqSoftDollarTiersProtoBuf(self, softDollarTiersRequestProto)
reqFamilyCodesProtoBuf(self, familyCodesRequestProto)
reqMatchingSymbolsProtoBuf(self, matchingSymbolsRequestProto)
reqCompletedOrdersProtoBuf(self, completedOrdersRequestProto)
reqWshMetaDataProtoBuf(self, wshMetaDataRequestProto)
cancelWshMetaDataProtoBuf(self, cancelWshMetaDataProto)
reqWshEventDataProtoBuf(self, wshEventDataRequestProto)
cancelWshEventDataProtoBuf(self, cancelWshEventDataProto)
reqUserInfoProtoBuf(self, userInfoRequestProto)
reqCurrentTimeInMillisProtoBuf(self, currentTimeInMillisRequestProto)
cancelContractDataProtoBuf(self, cancelContractDataProto)
cancelHistoricalTicksProtoBuf(self, cancelHistoricalTicksProto)
```

#### `EWrapper` (callbacks IB calls on you)

**Non-Protobuf callbacks**

```text
error(self, reqId, errorTime, errorCode, errorString, advancedOrderRejectJson)
winError(self, text, lastError)
connectAck(self)
marketDataType(self, reqId, marketDataType)
tickPrice(self, reqId, tickType, price, attrib)
tickSize(self, reqId, tickType, size)
tickSnapshotEnd(self, reqId)
tickGeneric(self, reqId, tickType, value)
tickString(self, reqId, tickType, value)
tickEFP(self, reqId, tickType, basisPoints, formattedBasisPoints, totalDividends, holdDays, futureLastTradeDate, dividendImpact, dividendsToLastTradeDate)
orderStatus(self, orderId, status, filled, remaining, avgFillPrice, permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice)
openOrder(self, orderId, contract, order, orderState)
openOrderEnd(self)
connectionClosed(self)
updateAccountValue(self, key, val, currency, accountName)
updatePortfolio(self, contract, position, marketPrice, marketValue, averageCost, unrealizedPNL, realizedPNL, accountName)
updateAccountTime(self, timeStamp)
accountDownloadEnd(self, accountName)
nextValidId(self, orderId)
contractDetails(self, reqId, contractDetails)
bondContractDetails(self, reqId, contractDetails)
contractDetailsEnd(self, reqId)
execDetails(self, reqId, contract, execution)
execDetailsEnd(self, reqId)
updateMktDepth(self, reqId, position, operation, side, price, size)
updateMktDepthL2(self, reqId, position, marketMaker, operation, side, price, size, isSmartDepth)
updateNewsBulletin(self, msgId, msgType, newsMessage, originExch)
managedAccounts(self, accountsList)
receiveFA(self, faData, cxml)
historicalData(self, reqId, bar)
historicalDataEnd(self, reqId, start, end)
scannerParameters(self, xml)
scannerData(self, reqId, rank, contractDetails, distance, benchmark, projection, legsStr)
scannerDataEnd(self, reqId)
realtimeBar(self, reqId, time, open_, high, low, close, volume, wap, count)
currentTime(self, time)
fundamentalData(self, reqId, data)
deltaNeutralValidation(self, reqId, deltaNeutralContract)
commissionAndFeesReport(self, commissionAndFeesReport)
position(self, account, contract, position, avgCost)
positionEnd(self)
accountSummary(self, reqId, account, tag, value, currency)
accountSummaryEnd(self, reqId)
verifyMessageAPI(self, apiData)
verifyCompleted(self, isSuccessful, errorText)
verifyAndAuthMessageAPI(self, apiData, xyzChallange)
verifyAndAuthCompleted(self, isSuccessful, errorText)
displayGroupList(self, reqId, groups)
displayGroupUpdated(self, reqId, contractInfo)
positionMulti(self, reqId, account, modelCode, contract, pos, avgCost)
positionMultiEnd(self, reqId)
accountUpdateMulti(self, reqId, account, modelCode, key, value, currency)
accountUpdateMultiEnd(self, reqId)
tickOptionComputation(self, reqId, tickType, tickAttrib, impliedVol, delta, optPrice, pvDividend, gamma, vega, theta, undPrice)
securityDefinitionOptionParameter(self, reqId, exchange, underlyingConId, tradingClass, multiplier, expirations, strikes)
securityDefinitionOptionParameterEnd(self, reqId)
softDollarTiers(self, reqId, tiers)
familyCodes(self, familyCodes)
symbolSamples(self, reqId, contractDescriptions)
mktDepthExchanges(self, depthMktDataDescriptions)
tickNews(self, tickerId, timeStamp, providerCode, articleId, headline, extraData)
smartComponents(self, reqId, smartComponentMap)
tickReqParams(self, tickerId, minTick, bboExchange, snapshotPermissions)
newsProviders(self, newsProviders)
newsArticle(self, requestId, articleType, articleText)
historicalNews(self, requestId, time, providerCode, articleId, headline)
historicalNewsEnd(self, requestId, hasMore)
headTimestamp(self, reqId, headTimestamp)
histogramData(self, reqId, items)
historicalDataUpdate(self, reqId, bar)
rerouteMktDataReq(self, reqId, conId, exchange)
rerouteMktDepthReq(self, reqId, conId, exchange)
marketRule(self, marketRuleId, priceIncrements)
pnl(self, reqId, dailyPnL, unrealizedPnL, realizedPnL)
pnlSingle(self, reqId, pos, dailyPnL, unrealizedPnL, realizedPnL, value)
historicalTicks(self, reqId, ticks, done)
historicalTicksBidAsk(self, reqId, ticks, done)
historicalTicksLast(self, reqId, ticks, done)
tickByTickAllLast(self, reqId, tickType, time, price, size, tickAttribLast, exchange, specialConditions)
tickByTickBidAsk(self, reqId, time, bidPrice, askPrice, bidSize, askSize, tickAttribBidAsk)
tickByTickMidPoint(self, reqId, time, midPoint)
orderBound(self, permId, clientId, orderId)
completedOrder(self, contract, order, orderState)
completedOrdersEnd(self)
replaceFAEnd(self, reqId, text)
wshMetaData(self, reqId, dataJson)
wshEventData(self, reqId, dataJson)
historicalSchedule(self, reqId, startDateTime, endDateTime, timeZone, sessions)
userInfo(self, reqId, whiteBrandingId)
currentTimeInMillis(self, timeInMillis)
```

**Protobuf callbacks (advanced)**

```text
orderStatusProtoBuf(self, orderStatusProto)
openOrderProtoBuf(self, openOrderProto)
openOrdersEndProtoBuf(self, openOrdersEndProto)
errorProtoBuf(self, errorMessageProto)
executionDetailsProtoBuf(self, executionDetailsProto)
executionDetailsEndProtoBuf(self, executionDetailsProto)
completedOrderProtoBuf(self, completedOrderProto)
completedOrdersEndProtoBuf(self, completedOrdersEndProto)
orderBoundProtoBuf(self, orderBoundProto)
contractDataProtoBuf(self, contractDataProto)
bondContractDataProtoBuf(self, contractDataProto)
contractDataEndProtoBuf(self, contractDataEndProto)
tickPriceProtoBuf(self, tickPriceProto)
tickSizeProtoBuf(self, tickSizeProto)
tickOptionComputationProtoBuf(self, tickOptionComputationProto)
tickGenericProtoBuf(self, tickGenericProto)
tickStringProtoBuf(self, tickStringProto)
tickSnapshotEndProtoBuf(self, tickSnapshotEndProto)
updateMarketDepthProtoBuf(self, marketDepthProto)
updateMarketDepthL2ProtoBuf(self, marketDepthL2Proto)
updateMarketDataTypeProtoBuf(self, marketDataTypeProto)
tickReqParamsProtoBuf(self, tickReqParamsProto)
updateAccountValueProtoBuf(self, accountValueProto)
updatePortfolioProtoBuf(self, portfolioValueProto)
updateAccountTimeProtoBuf(self, accountUpdateTimeProto)
accountDataEndProtoBuf(self, accountDataEndProto)
managedAccountsProtoBuf(self, managedAccountsProto)
positionProtoBuf(self, positionProto)
positionEndProtoBuf(self, positionEndProto)
accountSummaryProtoBuf(self, accountSummaryProto)
accountSummaryEndProtoBuf(self, accountSummaryEndProto)
positionMultiProtoBuf(self, positionMultiProto)
positionMultiEndProtoBuf(self, positionMultiEndProto)
accountUpdateMultiProtoBuf(self, accountUpdateMultiProto)
accountUpdateMultiEndProtoBuf(self, accountUpdateMultiEndProto)
historicalDataProtoBuf(self, historicalDataProto)
historicalDataUpdateProtoBuf(self, historicalDataUpdateProto)
historicalDataEndProtoBuf(self, historicalDataEndProto)
realTimeBarTickProtoBuf(self, realTimeBarTickProto)
headTimestampProtoBuf(self, headTimestampProto)
histogramDataProtoBuf(self, histogramDataProto)
historicalTicksProtoBuf(self, historicalTicksProto)
historicalTicksBidAskProtoBuf(self, historicalTicksBidAskProto)
historicalTicksLastProtoBuf(self, historicalTicksLastProto)
tickByTickDataProtoBuf(self, tickByTickDataProto)
updateNewsBulletinProtoBuf(self, newsBulletinProto)
newsArticleProtoBuf(self, newsArticleProto)
newsProvidersProtoBuf(self, newsProvidersProto)
historicalNewsProtoBuf(self, historicalNewsProto)
historicalNewsEndProtoBuf(self, historicalNewsEndProto)
wshMetaDataProtoBuf(self, wshMetaDataProto)
wshEventDataProtoBuf(self, wshEventDataProto)
tickNewsProtoBuf(self, tickNewsProto)
scannerParametersProtoBuf(self, scannerParametersProto)
scannerDataProtoBuf(self, scannerDataProto)
fundamentalsDataProtoBuf(self, fundamentalsDataProto)
pnlProtoBuf(self, pnlProto)
pnlSingleProtoBuf(self, pnlSingleProto)
receiveFAProtoBuf(self, receiveFAProto)
replaceFAEndProtoBuf(self, replaceFAEndProto)
commissionAndFeesReportProtoBuf(self, commissionAndFeesReportProto)
historicalScheduleProtoBuf(self, historicalScheduleProto)
rerouteMarketDataRequestProtoBuf(self, rerouteMarketDataRequestProto)
rerouteMarketDepthRequestProtoBuf(self, rerouteMarketDepthRequestProto)
secDefOptParameterProtoBuf(self, secDefOptParameterProto)
secDefOptParameterEndProtoBuf(self, secDefOptParameterEndProto)
softDollarTiersProtoBuf(self, softDollarTiersProto)
familyCodesProtoBuf(self, familyCodesProto)
symbolSamplesProtoBuf(self, symbolSamplesProto)
smartComponentsProtoBuf(self, smartComponentsProto)
marketRuleProtoBuf(self, marketRuleProto)
userInfoProtoBuf(self, userInfoProto)
nextValidIdProtoBuf(self, nextValidIdProto)
currentTimeProtoBuf(self, currentTimeProto)
currentTimeInMillisProtoBuf(self, currentTimeInMillisProto)
verifyMessageApiProtoBuf(self, verifyMessageApiProto)
verifyCompletedProtoBuf(self, verifyCompletedProto)
displayGroupListProtoBuf(self, displayGroupListProto)
displayGroupUpdatedProtoBuf(self, displayGroupUpdatedProto)
marketDepthExchangesProtoBuf(self, marketDepthExchangesProto)
```

If you need a missing **request → callbacks → end marker(s)** mapping documented above, add it following the same structure used in the “API reference” section.

---