def validate_price_data(df):


    if df is None:

        return False



    if df.empty:

        return False



    if len(df) < 60:

        return False



    required = [

        "Open",
        "High",
        "Low",
        "Close",
        "Volume"

    ]



    for col in required:


        if col not in df.columns:

            return False



    return True