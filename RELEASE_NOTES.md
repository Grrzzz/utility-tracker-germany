Utility Tracker Germany 1.0 - track your electricity, gas and water costs against your advance payments in Home Assistant.

### What is new

- **Trackers for electricity, gas and water:** set up as many as you like in the UI, each following a meter sensor of your choice. A two-step wizard asks for the contract and the prices
- **Sensors per tracker:** Plan (advances paid so far), Actual (consumption cost plus pro-rata base price), Balance (Plan minus Actual), Advance coverage (projected total cost compared to the planned advances), Remaining term and Tariff. Water also splits Actual into supply and sewage
- **Several contracts per tracker:** add, adjust or delete contracts later, for example after a price change. The sensors follow the running contract, overlapping contracts are rejected
- **Gas in kWh:** the meter is read in m³, you enter the price per kWh and your kWh/m³ conversion factor
- **Contract overview** in the options menu, with dates and numbers formatted for your Home Assistant language
- **English and German** user interface
- **Action `get_contract_data`:** returns the values of the running contract and of all contracts for dashboards and automations

### Installation

- **HACS:** add `https://github.com/Grrzzz/utility-tracker-germany` as a custom repository (type Integration), download and restart Home Assistant
- **Setup:** `Settings > Devices & services > Add integration > Utility Tracker Germany`, see the [README](https://github.com/Grrzzz/utility-tracker-germany/blob/v1.0.0/README.md)