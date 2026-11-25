"""Building the bill of lading and the pallet labels (Slice 3).

Plain-input functions: they take plain values and return dictionaries made only of strings,
numbers, booleans, lists and dictionaries, so the result can be stored as JSON and served as it is.
Nothing here touches the database or the clock; the booking service passes everything in.

The bill of lading is built once, when the booking is made, and stored on the booking. The labels
are built from that stored document alone, so they can never disagree with it. The bill of
lading shows no price and no fees: those belong on the booking confirmation.
"""

from dataclasses import dataclass
from datetime import date

from .contacts import Contact


@dataclass(frozen=True)
class Party:
    """The shipper or the consignee: a contact plus the address copied from the quote request."""

    contact: Contact
    street: str
    city: str
    state: str
    postal_code: str
    location_type: str


@dataclass(frozen=True)
class UnitLine:
    """One handling-unit line. Weight and dimensions are for ONE unit; `freight_class` is the
    class that priced the unit on the quote."""

    unit_type: str
    quantity: int
    weight_lb: int
    length_in: int
    width_in: int
    height_in: int
    freight_class: str
    commodity_description: str
    nmfc_code: str = ""
    stackable: bool = False


def booking_number_for(booking_id: int) -> str:
    """The booking number: BK- plus the id padded to six digits (also the bill of lading number)."""
    return f"BK-{booking_id:06d}"


def barcode_for(booking_number: str, unit_number: int, total_units: int) -> str:
    """The label barcode string, for example BK-000001-03-07 (unit 3 of 7)."""
    width = max(2, len(str(total_units)))
    return f"{booking_number}-{unit_number:0{width}d}-{total_units:0{width}d}"


def _party(party: Party) -> dict:
    return {
        "name": party.contact.name,
        "phone": party.contact.phone,
        "email": party.contact.email,
        "street": party.street,
        "city": party.city,
        "state": party.state,
        "postal_code": party.postal_code,
        "location_type": party.location_type,
    }


def build_bill_of_lading(
    *,
    booking_number: str,
    booking_date: date,
    pickup_date: date,
    carrier_code: str,
    carrier_name: str,
    shipper: Party,
    consignee: Party,
    units: list[UnitLine],
    liftgate_requested: bool,
    appointment_requested: bool,
    special_instructions: str,
) -> dict:
    """The bill of lading as a JSON-ready dictionary. Units keep the order of the quote request."""
    accessorials = []
    if liftgate_requested:
        accessorials.append("liftgate")
    if appointment_requested:
        accessorials.append("appointment")
    return {
        "number": booking_number,
        "booking_date": booking_date.isoformat(),
        "pickup_date": pickup_date.isoformat(),
        "carrier": {"code": carrier_code, "name": carrier_name},
        "shipper": _party(shipper),
        "consignee": _party(consignee),
        "units": [
            {
                "unit_type": unit.unit_type,
                "quantity": unit.quantity,
                "weight_lb": unit.weight_lb,
                "length_in": unit.length_in,
                "width_in": unit.width_in,
                "height_in": unit.height_in,
                "freight_class": unit.freight_class,
                "commodity_description": unit.commodity_description,
                "nmfc_code": unit.nmfc_code,
                "stackable": unit.stackable,
            }
            for unit in units
        ],
        "total_weight_lb": sum(unit.weight_lb * unit.quantity for unit in units),
        "accessorials": accessorials,
        "special_instructions": special_instructions,
    }


def build_labels(bill_of_lading: dict) -> list[dict]:
    """One label per physical handling unit, built from a stored bill of lading.

    A line with quantity 3 gives three labels. Units are numbered across the whole booking
    ("3 of 7"), in the order of the lines, and the count does not restart for each line.
    """
    number = bill_of_lading["number"]
    shipper = bill_of_lading["shipper"]
    consignee = bill_of_lading["consignee"]
    total_units = sum(unit["quantity"] for unit in bill_of_lading["units"])
    labels = []
    unit_number = 0
    for unit in bill_of_lading["units"]:
        for _ in range(unit["quantity"]):
            unit_number += 1
            labels.append(
                {
                    "booking_number": number,
                    "unit_number": unit_number,
                    "total_units": total_units,
                    "barcode": barcode_for(number, unit_number, total_units),
                    "unit_type": unit["unit_type"],
                    "weight_lb": unit["weight_lb"],
                    "freight_class": unit["freight_class"],
                    "commodity_description": unit["commodity_description"],
                    "shipper_name": shipper["name"],
                    "shipper_city": shipper["city"],
                    "shipper_state": shipper["state"],
                    "consignee_name": consignee["name"],
                    "consignee_city": consignee["city"],
                    "consignee_state": consignee["state"],
                    "destination_postal_code": consignee["postal_code"],
                    "carrier_name": bill_of_lading["carrier"]["name"],
                    "pickup_date": bill_of_lading["pickup_date"],
                }
            )
    return labels
