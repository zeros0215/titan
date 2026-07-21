"""
Market Update Tool
"""

from market.updater import MarketUpdater


def main():

    updater = MarketUpdater()

    updater.update()


if __name__ == "__main__":

    main()