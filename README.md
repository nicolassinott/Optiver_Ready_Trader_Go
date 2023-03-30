# Optiver's Ready Trader Go Challenge

## :open_book: Description 

This repository contais one possible solution from Optiver's Ready Trader Go challenge. The challenge consists in creating algorithmic trading strategies with a financial asset beetween to markets: 

* Future market (a very liquid market)
* ETF market (an iliquid market)

The goal here is to provide liquidity to the iliquid market and at the same time, make profit with your strategy.

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

## :bulb: Improvements

Our algorithm performs very well in illiquid markets (as in the train data provided by Optiver) 
and our strategy takes almost no risk. However, in during the competition rounds, due to the participation of new market makers, the spread between the Future and the ETF was almost zero. Therefore our algorithm spent a long time without carrying out transactions, which lowered our final pnl, even if it didn't lower the sharpe ratio.

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