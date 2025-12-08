from enum import Enum


class CronSchedule(Enum):
    """
    Common CRON expressions for task scheduling
    """
    EVERY_MINUTE = "* * * * *"
    EVERY_2_MINUTES = "*/2 * * * *"
    EVERY_5_MINUTES = "*/5 * * * *"
    EVERY_10_MINUTES = "*/10 * * * *"
    EVERY_15_MINUTES = "*/15 * * * *"
    EVERY_30_MINUTES = "*/30 * * * *"
    EVERY_HOUR = "0 * * * *"
    EVERY_2_HOURS = "0 */2 * * *"
    EVERY_6_HOURS = "0 */6 * * *"
    EVERY_8_HOURS = "0 */8 * * *"
    EVERY_12_HOURS = "0 */12 * * *"
    DAILY_MIDNIGHT = "0 0 * * *"
    DAILY_NOON = "0 12 * * *"
    DAILY_MORNING = "0 8 * * *"
    DAILY_EVENING = "0 20 * * *"
    DAILY_2PM = "0 14 * * *"
    DAILY_3PM = "0 15 * * *"
    DAILY_FIVE_PAST_3PM = "5 15 * * *"
    DAILY_SIX_PAST_3PM = "6 15 * * *"
    DAILY_TEN_PAST_3PM = "10 15 * * *"
    DAILY_4PM = "0 16 * * *"
    DAILY_TEN_PAST_4PM = "10 16 * * *"
    DAILY_4_40PM = "40 16 * * *"
    DAILY_5PM = "0 17 * * *"
    DAILY_TEN_PAST_5PM = "10 17 * * *"
    WEEKDAYS_ONLY = "0 0 * * 1-5"
    WEEKENDS_ONLY = "0 0 * * 0,6"
    WEEKLY_SUNDAY = "0 0 * * 0"
    WEEKLY_MONDAY = "0 0 * * 1"
    MONTHLY_FIRST_DAY = "0 0 1 * *"
    QUARTERLY = "0 0 1 1,4,7,10 *"
    YEARLY = "0 0 1 1 *"

    def __str__(self) -> str:
        """Returns the CRON expression as a string"""
        return self.value

    @staticmethod
    def from_name(name: str) -> str:
        """
        Gets a CRON expression from its name

        Args:
            name: Name of the expression (e.g.: "EVERY_MINUTE")

        Returns:
            str: CRON expression

        Raises:
            ValueError: If the name doesn't exist
        """
        try:
            return str(CronSchedule[name])
        except KeyError:
            valid_names = [s.name for s in CronSchedule]
            raise ValueError(
                f"Invalid CRON expression name. Options: {', '.join(valid_names)}")
