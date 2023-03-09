import asyncio
import itertools

from typing import List, Dict, Set

from ready_trader_go import BaseAutoTrader, Instrument, Lifespan, MAXIMUM_ASK, MINIMUM_BID, Side
from ready_trader_go.order_book import Order, OrderBook

LOT_SIZE = 100
POSITION_LIMIT = 100
TICK_SIZE_IN_CENTS = 100
MIN_BID_NEAREST_TICK = (MINIMUM_BID + TICK_SIZE_IN_CENTS) // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS
MAX_ASK_NEAREST_TICK = MAXIMUM_ASK // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS
MIN_PROFITABILITY = 2 * TICK_SIZE_IN_CENTS

class AutoTrader(BaseAutoTrader):
    def __init__(self, loop: asyncio.AbstractEventLoop, team_name: str, secret: str):
        super().__init__(loop, team_name, secret)
        self.order_ids = itertools.count(1)
        self.bids = None
        self.asks = None
        self.ask_id = self.ask_price = self.bid_id = self.bid_price = self.position = 0
        
        self.last_bids : Dict[int, List[int]] = {
            Instrument.FUTURE: [],
            Instrument.ETF: []
        }

        self.last_asks : Dict[int, List[int]] = {
            Instrument.FUTURE: [],
            Instrument.ETF: []
        }

    def on_order_book_update_message(
        self, 
        instrument: int, 
        sequence_number: int, 
        ask_prices: List[int], 
        ask_volumes: List[int], 
        bid_prices: List[int], 
        bid_volumes: List[int]
    ):

        # update our book
        self.last_bids[instrument] = bid_prices
        self.last_asks[instrument] = ask_prices

        self.logger.info(f"Round: {sequence_number}")
        self.logger.info(f"Future bids {self.last_bids[Instrument.FUTURE]}")
        self.logger.info(f"ETF bids {self.last_bids[Instrument.ETF]}")
        self.logger.info(f"Future asks {self.last_asks[Instrument.FUTURE]}")
        self.logger.info(f"ETF asks {self.last_asks[Instrument.ETF]}")

        # cancel order flow
        if self.bids is not None and self.last_bids[Instrument.FUTURE]:
            # is profitable
            if self.last_bids[Instrument.FUTURE][0] < self.bids.price + MIN_PROFITABILITY:
                self.send_cancel_order(self.bid_id)
                self.bid_id = 0
                self.bids = None

            if not self.last_bids[Instrument.ETF][2]\
                and self.last_bids[Instrument.ETF][2] > self.bids.price:
                self.send_cancel_order(self.bid_id)
                self.bid_id = 0
                self.bids = None

        if self.asks is not None and self.last_asks[Instrument.FUTURE]:
            # is profitable
            if self.last_asks[Instrument.FUTURE][0] > self.asks.price - MIN_PROFITABILITY:
                self.send_cancel_order(self.ask_id)
                self.ask_id = 0
                self.asks = None

            if not self.last_asks[Instrument.ETF][2]\
                and self.last_asks[Instrument.ETF][2] < self.asks.price:
                self.send_cancel_order(self.bid_id)
                self.ask_id = 0
                self.asks = None

        # create order flow
        if self.bids is None:
            if self.last_asks[Instrument.FUTURE] \
                and self.last_asks[Instrument.ETF] \
                and self.last_bids[Instrument.FUTURE][0] > self.last_bids[Instrument.ETF][0]:
                self.bid_id = next(self.order_ids)
                self.bid_price = self.last_bids[Instrument.ETF][0] - MIN_PROFITABILITY if self.last_bids[Instrument.ETF][0] >= MIN_PROFITABILITY else 0 
                bid_volume = 10
                bid_order = Order(self.bid_id,
                                  Instrument.ETF,
                                  Lifespan.GOOD_FOR_DAY,
                                  Side.BID,
                                  self.bid_price,
                                  bid_volume)
                print(self.bid_id, Side.BUY, self.bid_price, bid_volume)
                self.send_insert_order(self.bid_id,
                                       Side.BID,
                                       self.bid_price,
                                       bid_volume,
                                       Lifespan.GOOD_FOR_DAY)
                self.bids = bid_order
        
        
        if self.asks is None:
            if self.last_asks[Instrument.FUTURE] \
                and self.last_asks[Instrument.ETF]\
                and self.last_asks[Instrument.FUTURE][0] < self.last_asks[Instrument.ETF][0]:

                self.ask_id = next(self.order_ids)
                self.ask_price = self.last_asks[Instrument.ETF][0] + MIN_PROFITABILITY
                ask_volume = 10
                ask_order = Order(self.ask_id,
                                  Instrument.ETF,
                                  Lifespan.GOOD_FOR_DAY,
                                  Side.ASK,
                                  self.ask_price,
                                  ask_volume)
                self.send_insert_order(self.ask_id,
                                       Side.ASK,
                                       self.ask_price,
                                       ask_volume,
                                       Lifespan.GOOD_FOR_DAY)
                self.asks = ask_order
            
    def on_order_filled_message(
        self, 
        client_order_id: int, 
        price: int, 
        volume: int
    ):
        if client_order_id == self.bid_id:
            self.position += volume
            self.send_hedge_order(
                next(self.order_ids), 
                Side.ASK, 
                MIN_BID_NEAREST_TICK, 
                volume
            )
        elif client_order_id == self.ask_id:
            self.position -= volume
            self.send_hedge_order(
                next(self.order_ids), 
                Side.BID, 
                MAX_ASK_NEAREST_TICK, 
                volume
            )

    # def on_order_status_message(self, client_order_id: int, fill_volume: int, remaining_volume: int,
    #                             fees: int) -> None:
    #     """Called when the status of one of your orders changes.

    #     The fill_volume is the number of lots already traded, remaining_volume
    #     is the number of lots yet to be traded and fees is the total fees for
    #     this order. Remember that you pay fees for being a market taker, but
    #     you receive fees for being a market maker, so fees can be negative.

    #     If an order is cancelled its remaining volume will be zero.
    #     """
    #     self.logger.info("received order status for order %d with fill volume %d remaining %d and fees %d",
    #                      client_order_id, fill_volume, remaining_volume, fees)
    #     if remaining_volume == 0:
    #         if client_order_id == self.bid_id:
    #             self.bid_id = 0
    #         elif client_order_id == self.ask_id:
    #             self.ask_id = 0

    #         # It could be either a bid or an ask
    #         self.bids = None
    #         self.asks = None