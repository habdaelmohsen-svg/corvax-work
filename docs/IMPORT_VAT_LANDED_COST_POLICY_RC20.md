# RC20 Import VAT and Landed Cost Policy

## Core rule

The foreign supplier invoice and the Saudi import VAT event are separate records. A supplier invoice with no Saudi VAT does not by itself determine whether import VAT is payable, accounted through the return, suspended or exempt.

## Supported customs treatments

- `AT_CUSTOMS`: VAT was collected on the customs declaration.
- `THROUGH_RETURN`: customs declaration collection is zero and import VAT is self-accounted through the VAT return.
- `SUSPENDED`: VAT is suspended under a supported customs procedure; no immediate VAT is recorded.
- `EXEMPT`: a documented import exemption applies.

The user must store customs reference, declaration date, country of origin, VAT base, treatment and supporting evidence. Country of origin alone cannot select the treatment.

## Landed cost rule

Inventory cost includes directly attributable costs needed to bring inventory to its present location and condition, including eligible freight, insurance, duty, clearance and handling. Recoverable VAT is excluded. Nonrecoverable taxes and directly attributable charges may be capitalized under the approved accounting policy.
