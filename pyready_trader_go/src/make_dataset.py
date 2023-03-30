import pandas as pd
from typing import List
import numpy as np

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
    SHIFTS = [1,3,7,14,28,56]

    data_new = create_complete_data(data, SHIFTS)
    price_features = get_prices_features(data_new)
    bid_volume_feature, ask_volume_feature = get_volume_features(data_new)
    spread_feature = data_new['spread']

    X = price_features.copy()
    X['spread'] = spread_feature
    X['ask_volume'] = ask_volume_feature
    X['bid_volume'] = bid_volume_feature

    remaining_features = [
        'return_average_price_3',
        'return_average_price_7',
        'return_average_price_56',
        'ask_volume',
        'bid_volume',
        'target'
    ]
    
    y = data_new['target']

    return X[remaining_features], y