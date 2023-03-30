// Copyright 2021 Optiver Asia Pacific Pty. Ltd.
//
// This file is part of Ready Trader Go.
//
//     Ready Trader Go is free software: you can redistribute it and/or
//     modify it under the terms of the GNU Affero General Public License
//     as published by the Free Software Foundation, either version 3 of
//     the License, or (at your option) any later version.
//
//     Ready Trader Go is distributed in the hope that it will be useful,
//     but WITHOUT ANY WARRANTY; without even the implied warranty of
//     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
//     GNU Affero General Public License for more details.
//
//     You should have received a copy of the GNU Affero General Public
//     License along with Ready Trader Go.  If not, see
//     <https://www.gnu.org/licenses/>.
#include <array>

#include <boost/asio/io_context.hpp>

#include <ready_trader_go/logging.h>

#include "autotrader.h"

using namespace ReadyTraderGo;

RTG_INLINE_GLOBAL_LOGGER_WITH_CHANNEL(LG_AT, "AUTO")

constexpr int LOT_SIZE = 10;
constexpr int POSITION_LIMIT = 70;
constexpr int TICK_SIZE_IN_CENTS = 100;
constexpr int MIN_BID_NEARST_TICK = (MINIMUM_BID + TICK_SIZE_IN_CENTS) / TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS;
constexpr int MAX_ASK_NEAREST_TICK = MAXIMUM_ASK / TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS;

constexpr int MIN_PROFITABILITY = 2;
constexpr int MAX_ORDERS = 2;
constexpr int ORDER_VOLUME = 10;

constexpr int FUTURE = 0, ETF = 1;

AutoTrader::AutoTrader(boost::asio::io_context& context) : BaseAutoTrader(context)
{
}

void AutoTrader::DisconnectHandler()
{
    BaseAutoTrader::DisconnectHandler();
}

void AutoTrader::ErrorMessageHandler(unsigned long clientOrderId,
                                     const std::string& errorMessage)
{
    if (clientOrderId != 0 && ((mAsks.count(clientOrderId) == 1) || (mBids.count(clientOrderId) == 1)))
    {
        OrderStatusMessageHandler(clientOrderId, 0, 0, 0);
    }
}

void AutoTrader::HedgeFilledMessageHandler(unsigned long clientOrderId,
                                           unsigned long price,
                                           unsigned long volume)
{
}

void AutoTrader::OrderBookMessageHandler(Instrument instrument,
                                         unsigned long sequenceNumber,
                                         const std::array<unsigned long, TOP_LEVEL_COUNT>& askPrices,
                                         const std::array<unsigned long, TOP_LEVEL_COUNT>& askVolumes,
                                         const std::array<unsigned long, TOP_LEVEL_COUNT>& bidPrices,
                                         const std::array<unsigned long, TOP_LEVEL_COUNT>& bidVolumes)
{

    // a verificar (fazer for ou não ou fazer ref)
    unsigned long orderType =  instrument == Instrument::ETF;

    RLOG(LG_AT, LogLevel::LL_INFO) << mCanceledIds.size();

    for(unsigned long i = 0; i<2; ++i) {
        mLastAskPrices[orderType][i] = askPrices[i]; 
        mLastBidPrices[orderType][i] = bidPrices[i];
    }

    // Cancel order flow
    // Must check if proceed or not
    // Cancel bid
    for(auto& [bidId, bidPrice] : mBids){
        if(mCanceledIds.count(bidId)) continue;
        if(mLastBidPrices[FUTURE][0] <= bidPrice + MIN_PROFITABILITY * TICK_SIZE_IN_CENTS){ //* mPosition/POSITION_LIMIT){
            RLOG(LG_AT, LogLevel::LL_INFO) << "1: " << mBids.size();
            SendCancelOrder(bidId);
            RLOG(LG_AT, LogLevel::LL_INFO) << "2: " << mBids.size();
            mCanceledIds.insert(bidId);
        } else if (mLastBidPrices[ETF][1] > bidPrice){ 
            SendCancelOrder(bidId);
            mCanceledIds.insert(bidId); 
        }
    }

    // Cancel ask
    for(auto& [askId, askPrice] : mAsks){
        if(mCanceledIds.count(askId)) continue;
        if(mLastAskPrices[FUTURE][0] >= askPrice - MIN_PROFITABILITY * TICK_SIZE_IN_CENTS){ // * mPosition/POSITION_LIMIT){
            SendCancelOrder(askId);
            mCanceledIds.insert(askId);
        } else if (mLastAskPrices[ETF][1] < askPrice && mLastAskPrices[ETF][1]){
            SendCancelOrder(askId);
            mCanceledIds.insert(askId);
        }
    }

    
    // Create order flow
    // If no current position, checks if profitable
    if(mBids.size() < MAX_ORDERS && mPosition < POSITION_LIMIT){
        if(mLastBidPrices[FUTURE][0] > mLastBidPrices[ETF][0] + MIN_PROFITABILITY * TICK_SIZE_IN_CENTS 
        && mLastBidPrices[ETF][0] > MIN_PROFITABILITY * TICK_SIZE_IN_CENTS){
            unsigned long bidId = ++mNextMessageId;
            unsigned long bidPrice = mLastBidPrices[ETF][0] + TICK_SIZE_IN_CENTS;
            unsigned long bidVolume = ORDER_VOLUME;
            if(bidPrice > mLastAskPrices[ETF][0] && mLastAskPrices[ETF][0])
                bidPrice = mLastAskPrices[ETF][0];
            SendInsertOrder(bidId, Side::BUY, bidPrice, bidVolume, Lifespan::GOOD_FOR_DAY);
            mBids[bidId] = bidPrice;
        }
        else if(mPosition < -POSITION_LIMIT * 0.6 && mLastAskPrices[FUTURE][0]){
            unsigned long bidId = ++mNextMessageId;
            unsigned long bidPrice = mLastAskPrices[FUTURE][0] + TICK_SIZE_IN_CENTS;
            unsigned long bidVolume = 10;
            SendInsertOrder(bidId, Side::BUY, bidPrice, bidVolume, Lifespan::GOOD_FOR_DAY);
            mBids[bidId] = bidPrice;
        }
    }

    if(mAsks.size() < MAX_ORDERS && mPosition > -POSITION_LIMIT){
        if(mLastAskPrices[FUTURE][0] < mLastAskPrices[ETF][0] - MIN_PROFITABILITY * TICK_SIZE_IN_CENTS 
        && mLastAskPrices[ETF][0] > MIN_PROFITABILITY * TICK_SIZE_IN_CENTS){
            unsigned long askId = ++mNextMessageId;
            unsigned long askPrice = mLastAskPrices[ETF][0] + TICK_SIZE_IN_CENTS;
            unsigned long askVolume = ORDER_VOLUME;
            if(askPrice < mLastBidPrices[ETF][0] && mLastBidPrices[ETF][0])
                askPrice = mLastBidPrices[ETF][0];
            SendInsertOrder(askId, Side::SELL, askPrice, askVolume, Lifespan::GOOD_FOR_DAY);
            mAsks[askId] = askPrice;
        }
        else if(mPosition > POSITION_LIMIT * 0.6 && mLastBidPrices[FUTURE][0]){
            unsigned long askId = ++mNextMessageId;
            unsigned long askPrice = mLastBidPrices[FUTURE][0] + TICK_SIZE_IN_CENTS;
            unsigned long askVolume = 10;
            SendInsertOrder(askId, Side::SELL, askPrice, askVolume, Lifespan::GOOD_FOR_DAY);
            mAsks[askId] = askPrice;
        }
    }
}

void AutoTrader::OrderFilledMessageHandler(unsigned long clientOrderId,
                                           unsigned long price,
                                           unsigned long volume)
{
    if(mBids.count(clientOrderId)){
        SendHedgeOrder(++mNextMessageId, Side::SELL, MIN_BID_NEARST_TICK, volume);
        mPosition += volume;
        if(!mCanceledIds.count(clientOrderId)) SendCancelOrder(clientOrderId), mCanceledIds.insert(clientOrderId);
    }
    else if(mAsks.count(clientOrderId)){
        SendHedgeOrder(++mNextMessageId, Side::BUY, MAX_ASK_NEAREST_TICK, volume);
        mPosition -= volume;
        if(!mCanceledIds.count(clientOrderId)) SendCancelOrder(clientOrderId), mCanceledIds.insert(clientOrderId);
    }

}

void AutoTrader::OrderStatusMessageHandler(unsigned long clientOrderId,
                                           unsigned long fillVolume,
                                           unsigned long remainingVolume,
                                           signed long fees)
{
    if (remainingVolume) return;
    mBids.count(clientOrderId) ? mBids.erase(clientOrderId) : mAsks.erase(clientOrderId);
}

void AutoTrader::TradeTicksMessageHandler(Instrument instrument,
                                          unsigned long sequenceNumber,
                                          const std::array<unsigned long, TOP_LEVEL_COUNT>& askPrices,
                                          const std::array<unsigned long, TOP_LEVEL_COUNT>& askVolumes,
                                          const std::array<unsigned long, TOP_LEVEL_COUNT>& bidPrices,
                                          const std::array<unsigned long, TOP_LEVEL_COUNT>& bidVolumes)
{
}
