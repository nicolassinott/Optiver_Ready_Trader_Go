# Copyright 2021 Optiver Asia Pacific Pty. Ltd.
#
# This file is part of Ready Trader Go.
#
#     Ready Trader Go is free software: you can redistribute it and/or
#     modify it under the terms of the GNU Affero General Public License
#     as published by the Free Software Foundation, either version 3 of
#     the License, or (at your option) any later version.
#
#     Ready Trader Go is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU Affero General Public License for more details.
#
#     You should have received a copy of the GNU Affero General Public
#     License along with Ready Trader Go.  If not, see
#     <https://www.gnu.org/licenses/>.
import asyncio
import itertools

from typing import List

from ready_trader_go import BaseAutoTrader, Instrument, Lifespan, MAXIMUM_ASK, MINIMUM_BID, Side
# from ready_trader_go.order_book import Order, OrderBook

# LOT_SIZE = 10
POSITION_LIMIT = 70
TICK_SIZE_IN_CENTS = 100
MIN_BID_NEAREST_TICK = (MINIMUM_BID + TICK_SIZE_IN_CENTS) // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS
MAX_ASK_NEAREST_TICK = MAXIMUM_ASK // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS

MIN_PROFITABILITY = 2
MAX_ORDERS = 2
ORDER_VOLUME = 10
 
class AutoTrader(BaseAutoTrader):
    """Arbitrage Auto-trader.

    Performs arbitrage between exchanges. When it starts, it will 
    try to place profitable orders decreasing the spread and providing 
    liquidity to the ETF market.
    In every tick, it will replace non competitive orders.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, team_name: str, secret: str):
        """Initialise a new instance of the AutoTrader class."""
        super().__init__(loop, team_name, secret)
        self.order_ids = itertools.count(1)
        self.bids = dict()
        self.asks = dict()
        self.position = 0
        self.canceled_ids = set()

        self.last_bids = {
            Instrument.FUTURE: [MINIMUM_BID, MINIMUM_BID, MINIMUM_BID, MINIMUM_BID, MINIMUM_BID],
            Instrument.ETF: [MINIMUM_BID, MINIMUM_BID, MINIMUM_BID, MINIMUM_BID, MINIMUM_BID]
        }
 

        self.last_asks = {
            Instrument.FUTURE: [0, 0, 0, 0, 0],
            Instrument.ETF: [0, 0, 0, 0, 0]
        }
        

    def on_error_message(self, client_order_id: int, error_message: bytes) -> None:
        """Called when the exchange detects an error.

        If the error pertains to a particular order, then the client_order_id
        will identify that order, otherwise the client_order_id will be zero.
        """
        self.logger.warning(f"Error: {error_message.decode()}. Bids: {self.bids}, Asks: {self.asks}")
        self.logger.info(f"Bid prices: {self.last_bids}, Ask prices: {self.last_asks}")
        if client_order_id != 0 and (client_order_id in self.bids or client_order_id in self.asks):
            self.on_order_status_message(client_order_id, 0, 0, 0)

    def on_hedge_filled_message(self, client_order_id: int, price: int, volume: int) -> None:
        """Called when one of your hedge orders is filled.

        The price is the average price at which the order was (partially) filled,
        which may be better than the order's limit price. The volume is
        the number of lots filled at that price.
        """
        pass

    def on_order_book_update_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                                     ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        """Called periodically to report the status of an order book.

        The sequence number can be used to detect missed or out-of-order
        messages. The five best available ask (i.e. sell) and bid (i.e. buy)
        prices are reported along with the volume available at each of those
        price levels.
        """

        if instrument == Instrument.FUTURE:
            self.last_bids[Instrument.FUTURE] = bid_prices
            self.last_asks[Instrument.FUTURE] = ask_prices


        else:
            self.last_bids[Instrument.ETF] = bid_prices
            self.last_asks[Instrument.ETF] = ask_prices


        # Cancel order flow
        # Must check if proceed or not
        # Cancel bid
        for bid_id, bid_price in self.bids.items():
            if bid_id in self.canceled_ids:
                continue
            if self.last_bids[Instrument.FUTURE][0] <= bid_price + MIN_PROFITABILITY * TICK_SIZE_IN_CENTS: # and self.position >= -POSITION_LIMIT * 0.6: # 
                self.send_cancel_order(bid_id)
                self.canceled_ids.add(bid_id)
            elif self.last_bids[Instrument.ETF][1] > bid_price:
                self.send_cancel_order(bid_id)
                self.canceled_ids.add(bid_id)
        
        # Cancel ask
        for ask_id, ask_price in self.asks.items():
            if ask_id in self.canceled_ids:
                continue
            if self.last_asks[Instrument.FUTURE][0] >= ask_price - MIN_PROFITABILITY * TICK_SIZE_IN_CENTS: # and self.position <= POSITION_LIMIT * 0.6: # 
                self.send_cancel_order(ask_id)
                self.canceled_ids.add(ask_id)
            elif self.last_asks[Instrument.ETF][1] < ask_price and self.last_asks[Instrument.ETF][1] != 0: # check case when there is no second order
                self.send_cancel_order(ask_id)
                self.canceled_ids.add(ask_id)

        # Create order flow
        # If no current position, checks if profitable 

        if len(self.bids) < MAX_ORDERS and self.position < POSITION_LIMIT:
            if self.last_bids[Instrument.FUTURE][0] > self.last_bids[Instrument.ETF][0] + MIN_PROFITABILITY * TICK_SIZE_IN_CENTS and self.last_bids[Instrument.ETF][0] > MIN_PROFITABILITY * TICK_SIZE_IN_CENTS:
                bid_id = next(self.order_ids)
                bid_price = self.last_bids[Instrument.ETF][0] + TICK_SIZE_IN_CENTS # MIN_PROFITABILITY *
                bid_volume = ORDER_VOLUME
                if bid_price > self.last_asks[Instrument.ETF][0] and self.last_asks[Instrument.ETF][0] != 0:
                    bid_price = self.last_asks[Instrument.ETF][0] # maybe change volume in this case to the maximum possible?
                self.send_insert_order(bid_id,
                                       Side.BID,
                                       bid_price,
                                       bid_volume,
                                       Lifespan.GOOD_FOR_DAY)
                self.bids[bid_id] = bid_price
                self.logger.info(f"Sent order: SIDE = BID")
                self.logger.info(f"{sequence_number},BID,{bid_id},{self.last_bids[Instrument.ETF][0]},{self.last_asks[Instrument.ETF][0]},{self.last_bids[Instrument.FUTURE][0]},{self.last_asks[Instrument.FUTURE][0]},{bid_price},0")
            
            elif self.position < - POSITION_LIMIT * 0.6 and self.last_asks[Instrument.FUTURE][0] != 0:
                bid_id = next(self.order_ids)
                bid_price = self.last_asks[Instrument.FUTURE][0] + TICK_SIZE_IN_CENTS
                bid_volume = 10
                self.send_insert_order(bid_id,
                                       Side.BID,
                                       bid_price,
                                       bid_volume,
                                       Lifespan.GOOD_FOR_DAY)
                self.bids[bid_id] = bid_price
                self.logger.info(f"Sent order: SIDE = BID")
                self.logger.info(f"{sequence_number},BID,{bid_id},{self.last_bids[Instrument.ETF][0]},{self.last_asks[Instrument.ETF][0]},{self.last_bids[Instrument.FUTURE][0]},{self.last_asks[Instrument.FUTURE][0]},{bid_price},1")

        if len(self.asks) < MAX_ORDERS and self.position > -POSITION_LIMIT:
            if self.last_asks[Instrument.FUTURE][0] < self.last_asks[Instrument.ETF][0] - MIN_PROFITABILITY * TICK_SIZE_IN_CENTS and self.last_asks[Instrument.ETF][0] > MIN_PROFITABILITY * TICK_SIZE_IN_CENTS:
                ask_id = next(self.order_ids)
                ask_price = self.last_asks[Instrument.ETF][0] - TICK_SIZE_IN_CENTS # MIN_PROFITABILITY * pode melhorar essa margem
                ask_volume = ORDER_VOLUME
                if ask_price < self.last_bids[Instrument.ETF][0] and self.last_bids[Instrument.ETF][0] != 0:
                    ask_price = self.last_bids[Instrument.ETF][0]
                self.send_insert_order(ask_id,
                                       Side.ASK,
                                       ask_price,
                                       ask_volume,
                                       Lifespan.GOOD_FOR_DAY)
                self.asks[ask_id] = ask_price
                self.logger.info(f"Sent order: SIDE = ASK")
                self.logger.info(f"{sequence_number},ASK,{ask_id},{self.last_bids[Instrument.ETF][0]},{self.last_asks[Instrument.ETF][0]},{self.last_bids[Instrument.FUTURE][0]},{self.last_asks[Instrument.FUTURE][0]},{ask_price},0")

            elif self.position > POSITION_LIMIT * 0.6 and self.last_bids[Instrument.FUTURE][0] != 0:
                ask_id = next(self.order_ids)
                ask_price = self.last_bids[Instrument.FUTURE][0] - TICK_SIZE_IN_CENTS
                ask_volume = 10
                self.send_insert_order(ask_id,
                                       Side.ASK,
                                       ask_price,
                                       ask_volume,
                                       Lifespan.GOOD_FOR_DAY)
                self.asks[ask_id] = ask_price
                self.logger.info(f"Sent order: SIDE = ASK")
                self.logger.info(f"{sequence_number},ASK,{ask_id},{self.last_bids[Instrument.ETF][0]},{self.last_asks[Instrument.ETF][0]},{self.last_bids[Instrument.FUTURE][0]},{self.last_asks[Instrument.FUTURE][0]},{ask_price},1")

    def on_order_filled_message(self, client_order_id: int, price: int, volume: int) -> None:
        """Called when one of your orders is filled, partially or fully.

        The price is the price at which the order was (partially) filled,
        which may be better than the order's limit price. The volume is
        the number of lots filled at that price.
        """ 
        
        if client_order_id in self.bids:
            self.send_hedge_order(next(self.order_ids), Side.ASK, MIN_BID_NEAREST_TICK, volume)
            self.position += volume
            if client_order_id not in self.canceled_ids:
                self.send_cancel_order(client_order_id)
                self.canceled_ids.add(client_order_id)
            self.logger.info("Executed order BID")
            self.logger.info(f"BID,{client_order_id},{price},{volume},{self.last_bids[Instrument.FUTURE][0]}")

        elif client_order_id in self.asks:
            self.send_hedge_order(next(self.order_ids), Side.BID, MAX_ASK_NEAREST_TICK, volume)
            self.position -= volume
            if client_order_id not in self.canceled_ids:
                self.send_cancel_order(client_order_id)
                self.canceled_ids.add(client_order_id)
            self.logger.info("Executed order ASK")
            self.logger.info(f"ASK,{client_order_id},{price},{volume},{self.last_asks[Instrument.FUTURE][0]}")

    def on_order_status_message(self, client_order_id: int, fill_volume: int, remaining_volume: int,
                                fees: int) -> None:
        """Called when the status of one of your orders changes.

        The fill_volume is the number of lots already traded, remaining_volume
        is the number of lots yet to be traded and fees is the total fees for
        this order. Remember that you pay fees for being a market taker, but
        you receive fees for being a market maker, so fees can be negative.

        If an order is cancelled its remaining volume will be zero.
        """
        
        if remaining_volume == 0:
            if client_order_id in self.bids:
                self.bids.pop(client_order_id)
            elif client_order_id in self.asks:
                self.asks.pop(client_order_id) 

    def on_trade_ticks_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                               ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        """Called periodically when there is trading activity on the market.

        The five best ask (i.e. sell) and bid (i.e. buy) prices at which there
        has been trading activity are reported along with the aggregated volume
        traded at each of those price levels.

        If there are less than five prices on a side, then zeros will appear at
        the end of both the prices and volumes arrays.
        """
        pass
