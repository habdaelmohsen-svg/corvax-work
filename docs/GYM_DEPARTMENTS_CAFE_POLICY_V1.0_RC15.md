# Gym Departments, Facilities and Cafe Policy — RC15

## Department model

Every gym department belongs to a branch and must have its own cost center and revenue account. Supported types include swimming, strength, padel, cardio, group fitness, martial arts, kids, recovery, cafe and configurable other activities.

## Membership access

Each membership plan defines one of four access modes for each department:

- `INCLUDED`: covered by the membership.
- `ADDON`: requires an approved add-on commercial arrangement.
- `PAY_PER_USE`: charged per booking or visit.
- `EXCLUDED`: access denied.

Rules may also set monthly visit limits, advance-booking windows and guest permission. Frozen, expired, wrong-branch or excluded memberships are denied and the reason is retained.

## Facilities and booking

Facilities include pools, swimming lanes, padel courts, courts, studios, halls, zones and rooms. Bookings enforce status, capacity and time-overlap controls. Paid bookings require an independent approver. Revenue and VAT are posted to the department branch and cost center. Refunds reverse the original economic effect under controlled approval.

## Gym cafe

The gym cafe uses the existing item, recipe, inventory, VAT and POS engines. Products may be coffee, healthy meals, cold or hot drinks, protein products, snacks or other approved items. Product profiles may store member price, calories, macronutrients, sugar, caffeine and allergens.

Cafe sales are identified by the `GYM_CAFE` business unit and are reported separately from restaurant sales. Valid active members may receive the approved member price. Each sale records revenue, VAT, recipe-based inventory consumption, food cost and gross profit.

## Control principles

- No paid booking is approved by its maker.
- No started booking can be cancelled through the normal pre-start cancellation route.
- Facility overlap and unavailable/maintenance status block booking.
- Department and cafe operations retain branch and cost-center attribution.
- External access gates, payment devices and food-safety devices remain integration/UAT requirements.
