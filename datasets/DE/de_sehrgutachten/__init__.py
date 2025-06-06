# https://github.com/okfde/sehrgutachten/blob/master/app/scrapers/wd_ausarbeitungen_scraper.rb

import re
from datetime import datetime, timedelta
from urllib.parse import urljoin

from banal import ensure_dict
from furl import furl
from memorious.logic.context import Context
from servicelayer import env

from utils import Data
from utils import get_value_from_xpath as x
from utils.operations import cached_emit

MONTHS = (
    "januar",
    "februar",
    "märz",
    "april",
    "mai",
    "juni",
    "juli",
    "august",
    "september",
    "oktober",
    "november",
    "dezember",
)
WD_NAMES = {
    "wd1": "Geschichte, Zeitgeschichte und Politik",
    "wd2": "Auswärtiges, Völkerrecht, Wirtschaftliche Zusammenarbeit und Entwicklung, Verteidigung, Menschenrechte und humanitäre Hilfe",
    "wd3": "Verfassung und Verwaltung",
    "wd4": "Haushalt und Finanzen",
    "wd5": "Wirtschaft und Technologie, Ernährung, Landwirtschaft und Verbraucherschutz, Tourismus",
    "wd6": "Arbeit und Soziales",
    "wd7": "Zivil-, Straf- und Verfahrensrecht, Umweltschutzrecht, Verkehr, Bau und Stadtentwicklung",
    "wd8": "Umwelt, Naturschutz, Reaktorsicherheit, Bildung und Forschung",
    "wd9": "Gesundheit, Familie, Senioren, Frauen und Jugend",
    "wd10": "Kultur, Medien und Sport",
    "wd11": "Europa",
    "pe6": "Europa",
    "eu6": "Fachbereich Europa",
}


def _clean_date(value: str | None) -> str | None:
    if not value:
        return
    value = value.lower().replace(" ", "")
    for i, month in enumerate(MONTHS):
        if month in value:
            value = value.replace(month, "%s." % str(i + 1).zfill(2))
            return datetime.strptime(value, "%d.%m.%Y").date().isoformat()


def seed(context: Context, data: Data):
    f = furl(context.params["url"])
    if not env.to_bool("FULL_RUN"):
        start_date = env.get("START_DATE")
        if start_date:
            start_date = datetime.fromisoformat(start_date).date()
        else:
            start_date = (
                datetime.now()
                - timedelta(**ensure_dict(context.params.get("timedelta")))
            ).date()
        start_date = start_date.strftime("%s000")
        f.args["startdate"] = start_date
    f.args["limit"] = 10
    data["url"] = f.url
    context.emit(data=data)


def parse(context: Context, data: Data):
    res = context.http.rehash(data)

    rows = res.html.xpath('//table[@class="table bt-table-data"]/tbody/tr')

    for row in rows:
        path = x(row, './/a[@class="bt-link-dokument"]/@href')
        if not path:
            continue

        url = urljoin(data["url"], path)

        try:
            title = x(row, ".//div[@class='bt-documents-description']/p/strong")
            detail_data = {
                "url": url,
                "title": title,
                "key": url.split("/")[-1],
                "published_at": _clean_date(x(row, './td[@data-th="Datum"]/p')),
                "keywords": x(row, './td[@data-th="Thema"]/p'),
                "category": x(row, './td[@data-th="Dokumenttyp"]/p'),
                "publisher": context.crawler.config["publisher"],
                "reference": "",
            }

            wd_match = re.match(
                r"(?P<wd>wd|pe|eu)\s*(?P<wd_id>\d+)[\s-]+(?P<doc_id>\d+\/\d+)",
                detail_data["title"],
                re.IGNORECASE,
            )

            if wd_match:
                wd_id = wd_match.group("wd").lower() + wd_match.group("wd_id")
                wd_id_nice = f"{wd_match.group('wd')} {wd_match.group('wd_id')}"
                wd_name = WD_NAMES.get(wd_id, wd_id_nice)
                detail_data["publisher"].update(
                    {
                        "id": wd_id,
                        "name": f"{wd_id_nice} - {wd_name}",
                        "url": f"https://www.bundestag.de/dokumente/analysen/{wd_id}",
                    }
                )
                detail_data["reference"] = wd_match.group("doc_id")
                detail_data["foreign_id"] = "-".join((wd_id, wd_match.group("doc_id")))

            cached_emit(context, {**data, **detail_data}, "download")

        except Exception as e:
            context.log.error(f"Error at `{url}`: {e}")

    # pagination
    if len(rows):
        f = furl(data["url"])
        f.args["offset"] = int(f.args["limit"]) + int(f.args.get("offset", 0))
        context.emit("fetch", data={"url": f.url})
