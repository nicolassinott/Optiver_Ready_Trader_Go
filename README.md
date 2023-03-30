# Optiver's Ready Trader Go Challenge

## :open_book: Description 

This repository contais our solution to the Optiver's Ready Trader Go Challenge. The competition consists in creating algorithmic trading strategies with a financial asset beetween to markets: 

* Future market (liquid market)
* ETF market (iliquid market)

The goal is to create an algorithmic trading strategy to make profit while providing liquidity to the iliquid market.

## :chart_with_upwards_trend: The algorithm

The strategy consists of taking advantage of arbitrage opportunities between markets, reducing the spread and providing liquidity to the iliquid market. 

## :computer: Running the code

### :scroll: Requirements 

* Python 3.11
* [PySide6 package](https://pypi.org/project/PySide6/)
* One market data file 

To run the code, after installing the required libraries, clone the git repository:

``` bash
git clone git@github.com:nicolassinott/Optiver_Ready_Trader_Go.git
```

Then, navigate to the python folder:

``` bash
cd pyready_trader_go
```

Finally, run:

```bash
python3 rtg.py run [AUTOTRADER FILENAME [AUTOTRADER FILENAME]]
```

For example:

```bash
python3 rtg.py run autotrader.py
```

Our Python trader showed the best performance in training set, however a similar version in C++ is also provided in the cppready_trader_go folder. There, we experimented with different parameters (such as handling higher number of orders) that took advantage of the lower lattency of this programming language. The instructions to run this trader is provided in the README of its folder.

## :bulb: Improvements

Our algorithm performs very well in illiquid markets (as in the train data provided by Optiver) 
and our strategy takes almost no risk. In the competition rounds, due to the participation of new market makers, the spread between the Future and the ETF was almost zero, hence reducing the arbitrage opportunities that our model needed for making large profits. Therefore our algorithm spent a long time without carrying out transactions, which lowered our final pnl but didn't lower the sharpe ratio.

One possible improvement for this strategy is to use pair trading beetwen the spread Future - ETF:

$$
    spread = mid_{Future} - mid_{ETF}
$$

* Buy Future and sell ETF when the z-score* of the spread is less than a threshold ($\textit{e.g.}$ -1)
* Sell Future and buy ETF when the z-score* of the spread is higher than a threshold (($\textit{e.g.}$ 1))

*z-score of a series ${X}$ is given by:

$$
    zscore_{X} = (X_i - \bar{X})/\sigma_{X}
$$
