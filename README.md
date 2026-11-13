# Utility Tracker Germany

<img src="custom_components/utility_tracker_germany/brand/icon@2x.png" align="right" width="96" alt="Utility Tracker Germany icon">

A Home Assistant integration (installable via HACS) that answers one question for electricity, gas and water:

> **Am I paying too much or too little in advance?**

German utility contracts are billed with a fixed monthly advance payment (*Abschlag*, advance payment) and settled once a year against the actual consumption. This integration mirrors that logic live, so you see during the year whether you are heading for a refund or a back payment.

- One instance per contract and meter, as many as you like (electricity, gas, water, ...)
- Contract start on any date, with a configurable term in months
- Monthly advance, price per unit and yearly base price (*Grundpreis*)
- Mid-contract price changes, including meter reading at the cut-off date
- Water with separate fresh-water and wastewater prices
- Contract end countdown and a frozen result after the contract has ended
- Fully configured through the UI, no YAML and no template helpers

## Sensors

Every instance creates these sensors (all in EUR unless noted):

| Sensor | Meaning |
| --- | --- |
| **Plan** | Advance payments accrued so far (monthly advance x elapsed months, capped at the contract term). |
| **Actual** (*Ist*) | Actual cost so far: consumption x unit price + pro-rata base price. |
| **Balance** (*Guthaben*) | `Plan - Actual`. Positive = you are in credit, negative = back payment expected. |
| **Advance coverage** (*Abschlagsdeckung*) | Forecast in %: projected total *Actual* at contract end divided by the advances planned for the whole term. **100 %** = the advance fits exactly, **above 100 %** = back payment likely, **below 100 %** = refund likely. The projection extrapolates your average daily consumption since contract start and assumes the current prices stay valid until the end of the term. Attributes: `ist_forecast` (projected actual), `plan_total`, `balance_forecast` (expected refund, negative = back payment), `daily_consumption`, `remaining_days`. Unavailable for the first 14 days. |
| **Tariff** (*Tarif*) | The tariff of the currently running contract (unit price, monthly advance). |
| **Remaining term** (*Restlaufzeit*) | Days until the contract ends (unit `d`, attribute `contract_end`). |
| **Actual supply** / **Actual wastewater** (*Ist Bezug* / *Ist Abwasser*) | Water only: split of *Actual* into fresh water (incl. base price) and wastewater. |

*Remaining term* is meant as a trigger for your own automation, for example a notification when the value drops below 28 days. The integration deliberately does not send notifications by itself.

<!-- Screenshot: docs/images/dashboard.png -->

## Installation

1. In HACS open **Custom repositories**, add `https://github.com/Grrzzz/utility-tracker-germany` as type **Integration**.
2. Install **Utility Tracker Germany** and restart Home Assistant.
3. Go to **Settings -> Devices & services -> Add integration** and search for *Utility Tracker Germany*.

Requires Home Assistant 2024.1.0 or newer and a sensor that reports the meter reading (cumulative, e.g. `total_increasing`).

## Setup

The setup wizard has three steps.

### Step 1: Contract

| Field | Description |
| --- | --- |
| Name | Name of the instance, e.g. "Electricity". |
| Type | Electricity, gas or water. |
| Source sensor | Sensor with the cumulative meter reading. Units `Wh`, `kWh` and `MWh` are converted automatically. |
| Contract start | First day of the contract. |
| Term | Contract term in months (default 12). |
| Meter reading at contract start | Offset of the meter at the start date. It may be negative. |

<!-- Screenshot: docs/images/setup-step1.png -->

### Step 2: Prices

The form depends on the type. Electricity and gas ask for the price per kWh, water asks for the fresh-water price and the wastewater price per m3. All types ask for the yearly base price and the monthly advance.

For **gas** with a meter in m3, the form also asks for **kWh per m3** (calorific value x state number, printed on your gas bill). Enter the price per **kWh**; meter readings stay in m3 and the cost is calculated as consumption x kWh per m3 x price. Leave the factor at 1 if your source sensor already reports kWh.

For **water**, each m3 consumed is billed with both prices added together. There is a single base price for fresh water and wastewater combined.

<!-- Screenshot: docs/images/setup-step2.png -->

## Contracts

One tracker can hold **several contracts in sequence** (for example after a provider or tariff change). Each contract has its own start date, term, start reading, prices, base price and monthly advance.

The sensors (*Plan*, *Actual*, *Balance*, *Remaining term*, *Advance coverage*, *Tariff*) always refer to the **currently running contract**: the one with start <= today < end. If none is running, the last contract that started is used. Earlier and planned contracts are listed in the overview and in the action `get_contract_data`.

Trackers created with earlier versions are migrated automatically: their existing contract becomes contract 1.

## Changing things later

Open the integration and choose **Configure**. The menu has four entries:

- **Contract overview**: read-only summary of all contracts (running, ended, planned).
- **Add contract**: adds a follow-up contract. Start date and start reading are prefilled with the end of the last contract (and its end reading, or the value from long-term statistics), but can be changed freely. Overlapping contracts are rejected.
- **Adjust contract**: pick a contract, then edit start, term, start reading, prices, base price, monthly advance and the optional end reading.
- **Delete contract**: pick a contract and confirm. Deleting the last remaining contract removes the whole tracker. The source meter is not touched.

<!-- Screenshot: docs/images/options-menu.png -->

The optional **end reading** freezes *Actual*: after the contract end, consumption and base price only count up to the end date, and with an end reading consumption is calculated exactly up to that meter value. If a contract has no end reading and a later contract exists, the start reading of the next contract is used. If the last contract has ended and no end reading is set, the reading at the end date is suggested from long-term statistics.

<!-- Screenshot: docs/images/options-tariff-change.png -->

## Action: get_contract_data

The action `utility_tracker_germany.get_contract_data` returns tariffs, consumption, costs and forecast of your contracts as JSON. Optionally pass `entity_id` (one or more entities of this integration) to limit the result; without it all contracts are returned.

```yaml
action: utility_tracker_germany.get_contract_data
data: {}
response_variable: contracts
```

The response contains the headline values of the running contract (`active_contract`, `status`, `contract`, `tariff`, `meter`, `costs`, `forecast`) and `all_contracts`, a list with the same fields for every contract of the tracker (`status` is `past`, `active` or `planned`).

## How it is calculated

- **Plan** = sum of monthly advances for the elapsed full months plus the pro-rata part of the current month, capped at the term.
- **Actual** = (current reading - reading at the contract start) x unit price (+ wastewater price), plus base price pro-rated by days over a 365/366 day year.
- After the contract end, both stop growing.

Values refresh whenever the source sensor changes and at least every 15 minutes.

## License

[MIT](LICENSE)

