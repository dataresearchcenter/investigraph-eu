from investigraph.util import join_text
from investigraph.model import Context
from investigraph.types import CE, CEGenerator, Record


def get_values(record: Record, category: str, subcategory) -> list[str]:
    return [elem[subcategory] for elem in record[category]]


def add_payer_properties(proxy: CE, record: Record) -> CE:
    proxy.add("name", get_values(record, "Geldgeber", "fulltext"))
    proxy.add("sourceUrl", get_values(record, "Geldgeber", "fullurl"))
    proxy.add("topics", record["Branche"])
    proxy.add("keywords", record["Schlagworte"])
    return proxy


def create_payer(ctx: Context, record: Record) -> CE:
    if record["Kategorie"][0] == "natürliche Person":
        proxy = make_person(ctx, record)
    else:
        proxy = make_legalentity(ctx, record)
    return proxy


def make_address(ctx: Context, record: Record) -> CE | None:
    proxy = ctx.make("Address")
    proxy.id = ctx.make_slug(*record["Ort"], *record["Bundesland"], prefix="de-addr")
    if proxy.id is None:
        return
    proxy.add("city", record["Ort"])
    proxy.add("state", record["Bundesland"])
    proxy.add("country", "de")
    proxy.add("full", join_text(*record["Ort"], *record["Bundesland"], sep=", "))
    ctx.emit(proxy)
    return proxy


def make_organization(ctx: Context, record: Record) -> CE:
    proxy = ctx.make("Organization")
    proxy.id = ctx.make_slug("party", record["Empfänger"][0]["fulltext"])
    proxy.add("name", get_values(record, "Empfänger", "fulltext"))
    proxy.add("sourceUrl", get_values(record, "Empfänger", "fullurl"))
    proxy.add("topics", "pol.party")
    ctx.emit(proxy)
    return proxy


def make_legalentity(ctx: Context, record: Record) -> CE:
    proxy = ctx.make("LegalEntity")
    proxy.id = ctx.make_id(record["Geldgeber"][0]["fulltext"])
    proxy = add_payer_properties(proxy, record)
    address = make_address(ctx, record)
    if address:
        proxy.add("addressEntity", address)
        proxy.add("address", address.get("full"))
    ctx.emit(proxy)
    return proxy


def make_person(ctx: Context, record: Record) -> CE:
    proxy = ctx.make("Person")
    proxy.id = ctx.make_slug("person", record["Geldgeber"][0]["fulltext"])
    proxy = add_payer_properties(proxy, record)
    address = make_address(ctx, record)
    if address:
        proxy.add("addressEntity", address)
        proxy.add("address", address.get("full"))
    ctx.emit(proxy)
    return proxy


def make_payment(ctx: Context, record: Record, payer: str, beneficiary: str) -> CE:
    proxy = ctx.make("Payment")
    date = record["printouts"]["Jahr"]
    amounts = [str(round(a, 2)) for a in record["printouts"]["Betrag"]]
    proxy.id = ctx.make_slug(record["fulltext"])
    proxy.add("payer", payer)
    proxy.add("beneficiary", beneficiary)
    proxy.add("sourceUrl", record["fullurl"])
    proxy.add("amountEur", amounts)
    proxy.add("amount", amounts)
    proxy.add("currency", "EUR")
    proxy.add("date", date)
    ctx.emit(proxy)
    return proxy


def handle(ctx: Context, record: Record, ix: int) -> CEGenerator[CE]:
    tx = ctx.task()
    payer = create_payer(tx, record["printouts"])
    beneficiary = make_organization(tx, record["printouts"])
    make_payment(tx, record, payer.id, beneficiary.id)
    yield from tx
