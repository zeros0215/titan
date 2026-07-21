class VolumeFilter:

    MIN_VOLUME = 100000

    def check(self, series):

        return (

            series.latest.volume

            >=

            self.MIN_VOLUME

        )