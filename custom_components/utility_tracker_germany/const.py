"""Constants for Utility Tracker Germany."""

DOMAIN = "utility_tracker_germany"

CONF_NAME = "name"
CONF_SOURCE_SENSOR = "source_sensor"
CONF_START_READING = "start_reading"
CONF_START_DATE = "start_date"
CONF_UNIT_PRICE = "unit_price"
CONF_BASE_PRICE = "base_price_year"
CONF_MONTHLY_ADVANCE = "monthly_advance"
CONF_SEWAGE_PRICE = "sewage_price"
CONF_CONTRACTS = "contracts"
CONF_KWH_FACTOR = "kwh_per_m3"

UPDATE_INTERVAL_MINUTES = 15
CONF_TYPE = "type"
CONF_TERM_MONTHS = "term_months"

TYPE_ELECTRICITY = "electricity"
TYPE_GAS = "gas"
TYPE_WATER = "water"
TYPES = [TYPE_ELECTRICITY, TYPE_GAS, TYPE_WATER]

DEFAULT_TERM_MONTHS = 12

CONF_END_READING = "end_reading"
