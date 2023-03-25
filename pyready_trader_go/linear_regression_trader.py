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
import pandas as pd
import numpy as np

# LOT_SIZE = 10
POSITION_LIMIT = 70
TICK_SIZE_IN_CENTS = 100
MIN_BID_NEAREST_TICK = (MINIMUM_BID + TICK_SIZE_IN_CENTS) // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS
MAX_ASK_NEAREST_TICK = MAXIMUM_ASK // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS

MIN_PROFITABILITY = 10
MAX_ORDERS = 2
ORDER_VOLUME = 10

THRESHOLD_DECISION = 1
MAX_ORDER_DIRECTION = 90


UPDATE_BETA_TIME = 30
UPDATE_DIRECTION_TIME = 5

def create_return_features(data : pd.DataFrame, shifts : list) -> pd.DataFrame:
    '''
    Takes the raw dataframe (data) with the day shifts we want to compute returns (shifts).
    Return the dataframe with the new features.
    '''
    new_data = data.copy()

    for day in shifts:
        new_data[f'returns_{day}'] = data['mid_price'].div(data['mid_price'].shift(day)) - 1
        
        if day != 1:
            new_data[f'return_average_price_{day}'] = data['mid_price'].div(data['mid_price'].rolling(day).mean()) - 1

    return new_data.dropna(axis = 0)

def create_variable_next_day_price(data : pd.DataFrame) -> pd.DataFrame:
    '''
    Takes raw dataframe and adds a new column with the price on the next day
    '''
    new_data = data.copy()
    new_data['target'] = (data['mid_price'].shift(-1) - data['mid_price'])/data['mid_price']
    new_data.drop(columns='mid_price')

    return new_data.dropna(axis = 0)

def create_complete_data(data : pd.DataFrame, shifts : list) -> pd.DataFrame:
    '''
    Takes raw dataframe and generate the dataframe with new features and next day price
    '''
    new_data = data.copy()
    new_data = create_return_features(data, shifts)
    new_data = create_variable_next_day_price(new_data)

    return new_data

def get_prices_features(data: pd.DataFrame)->pd.DataFrame:
    """Returns prices features (returns and mean returns)

    Args:
        data (pd.DataFrame): _description_

    Returns:
        pd.Dataframe: _description_
    """    
    
    price_feature_names = ("return")
    price_feature_mask = data\
        .columns\
        .str\
        .startswith(price_feature_names)
    
    return data[data.columns[price_feature_mask]]

def get_volume_features(data: pd.DataFrame)-> List[pd.DataFrame]:
    """Returns volume features (bid volume and ask volume)

    Args:
        data (pd.DataFrame): _description_

    Returns:
        _type_: _description_
    """    
    bid_mask = data\
        .columns\
        .str\
        .contains("bid")
    
    bid_df = data[data.columns[bid_mask]]
    bid_volume_feature = (bid_df @ np.array([1,2,3,4,5])//9000)\
        .replace(0,6)
    
    ask_mask = data\
        .columns\
        .str\
        .contains("ask")

    ask_df = data[data.columns[ask_mask]]

    ask_volume_feature = (ask_df @ np.array([1,2,3,4,5]) // 9000)\
        .replace(0,6)
    
    return bid_volume_feature, ask_volume_feature

def transform(data : pd.DataFrame):
    """Main function. Returns X (features) and y
    
    Args:
        data (pd.DataFrame): Data columns: 
    ```
        [
            'bid_volume_0', 
            'bid_volume_1', 
            'bid_volume_2', 
            'bid_volume_3',
            'bid_volume_4', 
            'ask_volume_0', 
            'ask_volume_1', 
            'ask_volume_2',
            'ask_volume_3', 
            'ask_volume_4', 
            'mid_price', 
            'spread'
        ]
    ```

    Returns:
        [pd.DataFrame, pd.Series]: _description_
    """    
    SHIFTS = [1,3,7,14,28]

    data_new = create_complete_data(data, SHIFTS)
    price_features = get_prices_features(data_new)
    bid_volume_feature, ask_volume_feature = get_volume_features(data_new)
    spread_feature = data_new['spread']

    X = price_features.copy()
    X['spread'] = spread_feature
    X['ask_volume'] = ask_volume_feature
    X['bid_volume'] = bid_volume_feature
    X['const'] = 1

    remaining_features = [
        'return_average_price_3',
        'return_average_price_7',
        'return_average_price_28',
        'ask_volume',
        'bid_volume',
        'const'
        # 'target'
    ]
    
    y = data_new['target']

    return X[remaining_features], y

class AutoTrader(BaseAutoTrader):
    """Example Auto-trader.

    When it starts this auto-trader places ten-lot bid and ask orders at the
    current best-bid and best-ask prices respectively. Thereafter, if it has
    a long position (it has bought more lots than it has sold) it reduces its
    bid and ask prices. Conversely, if it has a short position (it has sold
    more lots than it has bought) then it increases its bid and ask prices.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, team_name: str, secret: str):
        """Initialise a new instance of the AutoTrader class."""
        super().__init__(loop, team_name, secret)
        self.order_ids = itertools.count(1)
    
        self.bids = dict()
        self.asks = dict()
        self.position = 0
        self.canceled_ids = set()

        # Hedging position
        self.last_hedge_time = 0
        self.position_future = 0
        self.volume_in_bid_orders = 0
        self.volume_in_ask_orders = 0
        self.bid_future_ids = set()
        self.ask_future_ids = set()
        
        # Linear model
        self.last_update_time = self.event_loop.time()
        self.column_names = [
            'bid_volume_0', 
            'bid_volume_1', 
            'bid_volume_2', 
            'bid_volume_3',
            'bid_volume_4', 
            'ask_volume_0', 
            'ask_volume_1', 
            'ask_volume_2',
            'ask_volume_3', 
            'ask_volume_4', 
            'mid_price', 
            'spread'
        ]
        self.data = pd.DataFrame(columns = self.column_names) # Must define the columns
        self.last_beta_update = self.event_loop.time()
        self.last_direction_update = self.event_loop.time()
        self.beta = 0
        self.X = 0
        self.y = 0

        # Decision direction
        self.direction = 0
        self.trend = 0 # 1 bid, -1 ask
        self.old_trend = 0

        self.initial_time = self.event_loop.time()

    def on_error_message(self, client_order_id: int, error_message: bytes) -> None:
        """Called when the exchange detects an error.

        If the error pertains to a particular order, then the client_order_id
        will identify that order, otherwise the client_order_id will be zero.
        """
        self.logger.warning(f"Error: {error_message.decode()}. Bids: {self.bids}, Asks: {self.asks}")
        if client_order_id != 0 and (client_order_id in self.bids or client_order_id in self.asks):
            self.on_order_status_message(client_order_id, 0, 0, 0)

    def on_hedge_filled_message(self, client_order_id: int, price: int, volume: int) -> None:
        """Called when one of your hedge orders is filled.

        The price is the average price at which the order was (partially) filled,
        which may be better than the order's limit price. The volume is
        the number of lots filled at that price.
        """
        if client_order_id in self.bid_future_ids:
            self.position_future += volume
        elif client_order_id in self.ask_future_ids:
            self.position_future -= volume # must check if volume is negative (!!!!!!!!)

    

    def generate_fit(self, data) -> np.ndarray:
        '''
        Generates the fit
        '''
        print(f"changing beta: {data.shape[0]}")
        X, y = transform(data.tail(200)) 
        new_X = np.array(X)
        # new_X = np.insert(new_X, 0, np.ones(new_X.shape[0]), axis=1)

        self.beta = np.linalg.multi_dot([np.linalg.inv(new_X.transpose().dot(new_X)), new_X.transpose(), y]) 
        print(self.beta)
        

    def get_decision(self, X : np.ndarray) -> int:
        '''
        Returns 1 if long -1 if short
        '''
        return X.iloc[-1].dot(self.beta)


    def on_order_book_update_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                                     ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        """Called periodically to report the status of an order book.

        The sequence number can be used to detect missed or out-of-order
        messages. The five best available ask (i.e. sell) and bid (i.e. buy)
        prices are reported along with the volume available at each of those
        price levels.
        """

        current_time = self.event_loop.time()

        ### HEDGE HEDGE HEDGE HEDGE HEDGE HEDGE HEDGE HEDGE HEDGE HEDGE HEDGE HEDGE HEDGE  ###
        # First performs the check of unhedge 
        time_delta = current_time - self.last_hedge_time     
        
        if time_delta > 45:
            # Cancela tudo que estiver ativo
            for id in self.bids:
                if id not in self.canceled_ids:
                    self.send_cancel_order(id)
                    self.canceled_ids.add(id)
            for id in self.asks:
                if id not in self.canceled_ids:
                    self.send_cancel_order(id)
                    self.canceled_ids.add(id)
            
            # Hedge a posição
            if not self.bids and not self.asks:
                if self.position > 0 and not self.bid_future_ids:
                    id_hedge = next(self.order_ids)
                    self.send_hedge_order(id_hedge, Side.ASK, MIN_BID_NEAREST_TICK, self.position)
                    self.bid_future_ids.add(id_hedge)
                    
                elif self.position < 0 and not self.ask_future_ids:
                    id_hedge = next(self.order_ids)
                    self.send_hedge_order(id_hedge, Side.BID, MAX_ASK_NEAREST_TICK, -self.position)
                    self.ask_future_ids.add(id_hedge)

        if self.position == - self.position_future:
            self.last_hedge_time = current_time

        ### HEDGE HEDGE HEDGE HEDGE HEDGE HEDGE HEDGE HEDGE HEDGE HEDGE HEDGE HEDGE HEDGE  ###

        if instrument == Instrument.FUTURE:
            return

        # idx_bid = 5
        # idx_ask = 5
        
        # for idx, bid_volume in enumerate(bid_volumes):
        #     if bid_volume > 5000:
        #         idx_bid = idx
        #         break
        # for idx, ask_volume in enumerate(ask_volumes):
        #     if ask_volume > 5000:
        #         idx_ask = idx
        #         break

        new_decision = 0

        data_entry = pd.Series([bid_volumes[0], bid_volumes[1], bid_volumes[2], bid_volumes[3], bid_volumes[4], ask_volumes[0], ask_volumes[1], ask_volumes[2], ask_volumes[3], ask_volumes[4], (ask_prices[0] + bid_prices[0])/2, ask_prices[0] - bid_prices[0]])
        # data_entry = pd.DataFrame(data_entry, columns=self.column_names)

        # data_entry = np.array([self.event_loop.time(), bid_prices[0], ask_prices[0], idx_bid, idx_ask])
        
        if current_time - self.last_update_time > UPDATE_BETA_TIME and self.data.shape[0] > 60:
            self.last_update_time = current_time
            self.generate_fit(self.data)

        data_entry = pd.DataFrame(data_entry).T
        data_entry.columns = self.data.columns
        self.data = pd.concat([self.data, data_entry], axis = 0, ignore_index=True) # CHECK ORDER IN CODE

        if current_time - self.last_direction_update > UPDATE_DIRECTION_TIME and self.data.shape[0] > 61 and type(self.beta) != int:
            new_data = self.data.iloc[-40:]
            
            X, y = transform(new_data)
            # print(X)
            # print(self.beta)
            # print(X.shape)
            # print(self.beta.shape)
            self.last_direction_update = current_time
            new_decision = self.get_decision(X)
            print(f'new_decision: {new_decision}')
            new_decision = np.sign(new_decision)

        if new_decision == 1 and self.direction < THRESHOLD_DECISION:
            self.direction += 1
        elif new_decision == -1 and self.direction > -THRESHOLD_DECISION:
            self.direction -= 1

        # Updating direction
        if self.direction == THRESHOLD_DECISION:
            self.trend = 1
        elif self.direction == -THRESHOLD_DECISION:
            self.trend = -1
            

        # CODE THE CANCEL ORDER FOR EACH CONDITION

        # Perfoming the trades in normal direction

        if self.old_trend == self.trend:
            if self.trend == 1 and self.position < MAX_ORDER_DIRECTION and not self.bids: ## IMPROVE CONDITION ON bid_prices[2] and bid_prices[2] 
                bid_id = next(self.order_ids)
                bid_volume = MAX_ORDER_DIRECTION - self.position # MUST UPDATE WHEN ORDER IS PARTIALLY FILLED
                # bid_price = bid_prices[2]
                self.send_insert_order(bid_id,
                                    Side.BID,
                                    MAX_ASK_NEAREST_TICK,
                                    bid_volume,
                                    Lifespan.FILL_AND_KILL)
                
                # self.volume_in_bid_orders += bid_volume # volume in bid_orders may be different than position
                self.bids[bid_id] = MAX_ASK_NEAREST_TICK
            
            if self.trend == -1 and self.position > -MAX_ORDER_DIRECTION and not self.asks: # and ask_prices[2] 
                ask_id = next(self.order_ids)
                ask_volume = MAX_ORDER_DIRECTION + self.position
                # self.volume_in_ask_orders = MAX_ORDER_DIRECTION

                # ask_price = ask_prices[2]
                self.send_insert_order(ask_id,
                                        Side.ASK,
                                        MIN_BID_NEAREST_TICK,
                                        ask_volume,
                                        Lifespan.FILL_AND_KILL)
                self.asks[ask_id] = MIN_BID_NEAREST_TICK

        # When directions are inverted

        # else:
        if self.trend == 1 and self.old_trend == -1 and not self.bids:
            # if self.position < MAX...:
            bid_id = next(self.order_ids)
            bid_volume = MAX_ORDER_DIRECTION - self.position
            self.send_insert_order(bid_id,
                                    Side.BID,
                                    MAX_ASK_NEAREST_TICK,
                                    bid_volume,
                                    Lifespan.FILL_AND_KILL)
            self.bids[bid_id] = MAX_ASK_NEAREST_TICK
            # self.volume_in_bid_orders += bid_volume

        elif self.trend == -1 and self.old_trend == 1 and not self.asks:
            ask_id = next(self.order_ids)
            ask_volume = MAX_ORDER_DIRECTION + self.position
            self.send_insert_order(ask_id,
                                    Side.ASK,
                                    MIN_BID_NEAREST_TICK,
                                    ask_volume,
                                    Lifespan.FILL_AND_KILL
                                    )
            self.asks[ask_id] = MIN_BID_NEAREST_TICK
            # self.volume_in_ask_orders += ask_volume

        # Must think when orders are cancelled

        # print(self.event_loop.time() - current_time)
        # print(f"Trend is: {self.trend} / Direction is: {self.direction}")
        self.old_trend = self.trend

    def on_order_filled_message(self, client_order_id: int, price: int, volume: int) -> None:
        """Called when one of your orders is filled, partially or fully.

        The price is the price at which the order was (partially) filled,
        which may be better than the order's limit price. The volume is
        the number of lots filled at that price.
        """ 
        
        if client_order_id in self.bids:
            # self.send_hedge_order(next(self.order_ids), Side.ASK, MIN_BID_NEAREST_TICK, volume)
            self.position += volume
            if client_order_id not in self.canceled_ids:
                # self.send_cancel_order(client_order_id)
                self.canceled_ids.add(client_order_id) # ASSUMINDO QUE FILL AND KILL CANCELA POR NOS

        elif client_order_id in self.asks:
            # self.send_hedge_order(next(self.order_ids), Side.BID, MAX_ASK_NEAREST_TICK, volume)
            self.position -= volume
            if client_order_id not in self.canceled_ids:
            #     self.send_cancel_order(client_order_id)
                self.canceled_ids.add(client_order_id) # ASSUMINDO QUE FILL AND KILL CANCELA POR NOS
            # self.logger.info("Executed order ASK")
            # self.logger.info(f"ASK,{client_order_id},{price},{volume},{self.last_asks[Instrument.FUTURE][0]}")

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
            elif client_order_id in self.bid_future_ids:
                self.bid_future_ids.remove(client_order_id) 
            elif client_order_id in self.ask_future_ids:
                self.ask_future_ids.remove(client_order_id) 

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
